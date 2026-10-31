"""Conservative checks for repeated storyboard beats, independent of image generation."""
import json
import re
from difflib import SequenceMatcher


def text_key(text):
    return ' '.join(re.findall(r'\w+', text.casefold()))


def same_text(a, b):
    a, b = text_key(a), text_key(b)
    if not a or not b:
        return False
    return a == b or (min(len(a.split()), len(b.split())) >= 10
                      and SequenceMatcher(None, a, b, autojunk=False).ratio() >= .90)


def lettering(panel):
    return (text_key(panel.get('caption', '')),
            tuple((text_key(b.get('speaker', '')), text_key(b['text'])) for b in panel.get('bubbles', [])))


def repeated_panels(candidate_scenes, previous_scenes=()):
    """Report new duplicates; allow intentional repeated framing with distinct dialogue or shots."""
    seen, repeated = [], []
    for previous, scenes in ((True, previous_scenes), (False, candidate_scenes)):
        for si, scene in enumerate(scenes, 1):
            for pi, panel in enumerate(scene['panels'], 1):
                label = ('Vorheriger Abschnitt ' if previous else '')+f'Szene {si}, Panel {pi}'
                hit = next((name for name, old in seen if
                    old.get('shot', 'medium') == panel.get('shot', 'medium')
                    and lettering(old) == lettering(panel)
                    and (same_text(old['description'], panel['description']) or
                         same_text(old['visual_prompt'], panel['visual_prompt']))), None)
                if hit and not previous:
                    repeated.append(f'{label} wiederholt {hit}')
                seen.append((label, panel))
    return repeated


def copied_character_profiles(candidate_scenes,cast):
    profiles=[text_key(c.get('description','')) for c in cast]
    profiles=[p for p in profiles if len(p.split())>=18]
    return [f'Szene {si}, Panel {pi}: Bildprompt kopiert ein Charakterprofil statt einer konkreten Szenenaktion'
        for si,scene in enumerate(candidate_scenes,1) for pi,panel in enumerate(scene['panels'],1)
        if any(p in text_key(panel['visual_prompt']) or same_text(p,panel['visual_prompt']) for p in profiles)]


def plan_distinct_chunk(worker, job, prompt, cast, source, previous_scenes, at, client, settings, part_count=1):
    from .engine import text_graph, decode_plan, validate_chunk, StoryboardOrderError
    from pydantic import ValidationError
    state = job['payload'].get('plan_quality', {})
    if state.get('chunk') != at:
        state = {'chunk': at, 'attempt': 0, 'feedback': ''}
    # An explicit retry gives an exhausted chunk another bounded attempt budget.
    if state['attempt'] >= 3:
        state['attempt'] = 0
        state['feedback'] = ('\nErneuter Versuch: Plane kompakt anhand des Originaltexts. '
            'Keine Füllpanels. Bildprompts beschreiben konkrete Szenenaktionen, keine Charakterporträts. '
            'Bereits dargestellte Momente nicht wiederholen. Aussehen und Referenzen werden separat ergänzt.')
    job['payload']['plan_quality'] = state
    while state['attempt'] < 3:
        attempt = state['attempt']
        operation = f'plan:{at}' if attempt == 0 else f'plan:{at}:repair:{attempt}'
        answer = worker.run(job, text_graph(settings.text_model, prompt+state['feedback']), operation, client, settings)
        value = None
        try:
            value = decode_plan(answer.text_outputs[-1].strip(), cast, source)
            validate_chunk(value, source, {c['id'] for c in cast})
        except ValidationError as exc:
            problems = ['.'.join(str(p) for p in issue['loc'])+': '+issue['msg']
                        for issue in exc.errors(include_input=False, include_url=False)[:12]]
            correction = ('Korrigiere die genannten Schemafehler und liefere den vollständigen Abschnitt erneut. '
                'Für shot ausschließlich wide, medium, close oder detail verwenden. '
                'Alle Felder müssen dem JSON-Schema entsprechen; keine eigenen Auswahlwerte erfinden. '
                'Handlung und Originalfundstellen beibehalten und nicht durch Füllpanels ersetzen. ')
            label = 'Schemafehler'
        except StoryboardOrderError:
            problems = ['Die KI-Szenen stehen nicht in Buchreihenfolge.']
            correction = ('Plane die Szenen anhand des Originaltextes erneut in aufsteigender source_start-Reihenfolge. '
                'Prüfe die Handlung und ihre echten Quellbereiche gemeinsam; keine Absatznummern erfinden oder nur '
                'umnummerieren, um die Prüfung zu umgehen. Keine Rücksprünge oder zusätzlichen Ereignisse einbauen. ')
            label = 'Szenenreihenfolge'
        else:
            candidate=value.model_dump()['scenes']
            copies=copied_character_profiles(candidate,cast)
            problems = repeated_panels(candidate, previous_scenes)+copies
            correction = ('Verwirf die Wiederholungen. Plane diesen Abschnitt anhand seiner Originalabsätze neu. '
                'Jedes Panel zeigt einen anderen belegten Handlungsschritt, eine Reaktion oder ein relevantes Detail. '
                'Nicht dieselbe Handlung umformulieren oder nur Namen austauschen. Weniger Panels sind besser als Füllbilder. '
                'Bereits im vorherigen Abschnitt dargestellte Momente nicht erneut erzählen. '
                'visual_prompt beschreibt NUR Name und konkrete Aktion, Hände, Blick, Umgebung und Kamera. '
                'Keine Charakterbeschreibung als Bildprompt kopieren; Aussehen ergänzt die Bildgenerierung separat. '
                'Ein bis zwei präzise Panels pro Szene sind besser als vier ähnliche Standbilder. ')
            label = 'Profilkopien' if copies else 'Wiederholungen'
        if not problems:
            job['payload'].pop('plan_quality', None)
            return value
        # Never checkpoint rejected scenes. Keep feedback and the next operation durable.
        state['attempt'] += 1
        state['feedback'] = ('\nÜBERARBEITUNG ERFORDERLICH: '+ '; '.join(problems[:12])+'\n'+correction+
            'Auch die Quellbereiche und Szenentitel müssen zu den Handlungen passen. '
            'Antworte erneut mit dem vollständigen JSON für diesen Abschnitt.'+
            '\nBEREITS DARGESTELLT: '+json.dumps([p['description'] for s in previous_scenes for p in s['panels']][-16:], ensure_ascii=False))
        job['payload'].pop('remote', None)
        worker.store.update_job(job['id'], payload=job['payload'])
        if state['attempt'] < 3:
            worker.update(job, f'Storyboard: {label} in Abschnitt {at+1} überarbeiten ({state["attempt"]}/2)',
                          at/max(1, part_count))
    raise ValueError({'Szenenreihenfolge': 'Die KI-Szenen stehen nach zwei Überarbeitungen weiterhin nicht in Buchreihenfolge. ',
                     'Schemafehler': 'Die KI-Antwort enthält nach zwei Überarbeitungen weiterhin Schemafehler: '+'; '.join(problems[:6])+'. ',
                     'Profilkopien': 'Die KI kopiert nach zwei Überarbeitungen weiterhin Charakterprofile als Bildprompts. ',
                     'Wiederholungen': 'Die KI wiederholt nach zwei Überarbeitungen weiterhin denselben Panelinhalt. '}[label]+
                     'Dieser Abschnitt wurde nicht übernommen. Fortsetzen versucht ihn erneut.')
