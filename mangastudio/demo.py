"""Explicitly labelled storyboard/layout sample, no claims of AI-generated artwork."""
from .models import Scene, Panel, Bubble, uid
from .importer import import_book

TEXT = '''Kapitel 1 - Die verschwundene Stunde

Der Uhrturm schlug dreizehnmal, als Mara die verlassene Station betrat. Auf dem Bahnsteig stand ein Junge mit einem silbernen Koffer. Er nannte sich Ivo und behauptete, auf einen Zug von gestern zu warten.

Mara öffnete ihr Notizbuch. Die letzte Seite zeigte den Bahnsteig, gezeichnet mit ihrer eigenen Handschrift. Unter der Zeichnung stand: Steig nicht ein.

Ein Licht erschien im Tunnel. Ivo legte die Hand auf den Koffer. Mara hörte ihre eigene Stimme aus dem Lautsprecher: Bitte zurückbleiben.

Kapitel 2 - Ein Fahrplan aus Schatten

Der Zug hielt ohne Geräusch. In jedem Fenster saß dieselbe Frau, nur jedes Mal ein wenig älter. Mara erkannte ihre Mutter.

Ivo stellte den silbernen Koffer zwischen die Türen. Darin lag keine Uhr, sondern ein warmer Stein. Als Mara ihn berührte, blieb der Regen vor dem Fenster in der Luft stehen.

Mara trat zurück auf den Bahnsteig. Sie schrieb ein einziges Wort in ihr Notizbuch: Morgen. Die Türen schlossen sich, und Ivo lächelte zum ersten Mal.
'''


def create_demo(store):
    for old in store.list('projects'):
        if old.get('demo'):
            return old
    project = import_book(store, 'Die verschwundene Stunde.txt', TEXT.encode())
    project['demo'] = True
    project['warnings'] = ['Layout-Demo mit geschriebenem Storyboard. Die grauen Felder sind Platzhalter, keine KI-generierten Manga-Bilder.']
    store.write('projects', project)
    mara, ivo = uid(), uid()
    for ident, name, desc in ((mara, 'Mara', 'Erwachsene Archivarin, 28 Jahre, kurzes dunkles Haar, langer heller Mantel, Notizbuch.'),
                               (ivo, 'Ivo', 'Junger erwachsener Reisender, 23 Jahre, lockiges Haar, dunkle Jacke, silberner Koffer.')):
        store.write('characters', {'id': ident, 'name': name, 'description': desc, 'aliases': '', 'image': ''}, project['id'])
    descriptions = [
        ['Eine verlassene Station unter einem riesigen Uhrturm im Regen.', 'Mara betritt den Bahnsteig. Ivo wartet mit seinem Koffer.',
         'Nahaufnahme: dreizehn Striche auf dem Zifferblatt.', 'Mara sieht Ivo fragend an.', 'Ivo zeigt auf einen leeren Fahrplan.',
         'Maras Notizbuch zeigt eine Zeichnung des Bahnsteigs.', 'Eine Warnung auf der letzten Seite.', 'Ein einzelnes Licht nähert sich im dunklen Tunnel.'],
        ['Ein Zug aus Licht hält an der Station.', 'In den Fenstern sitzt dieselbe Frau in verschiedenen Lebensaltern.',
         'Mara erkennt das Gesicht ihrer Mutter.', 'Ivo öffnet den silbernen Koffer.', 'Ein warmer Stein liegt auf dunklem Stoff.',
         'Regentropfen stehen unbewegt in der Luft.', 'Mara schreibt in ihr Notizbuch.', 'Die Türen schließen sich. Ivo lächelt.']]
    for index, chapter in enumerate(store.list('chapters', project['id'])):
        source = chapter['text'].split('\n\n')
        scenes = []
        for s, indices in enumerate(([0], [1, 2, 3, 4], [5, 6, 7])):
            panels = []
            for i in indices:
                bubbles = []
                if i == 3:
                    bubbles = [Bubble(speaker='Mara', text='Worauf wartest du?', side='right')]
                if i == 4:
                    bubbles = [Bubble(speaker='Ivo', text='Auf einen Zug von gestern.', side='left')]
                panels.append(Panel(description=descriptions[index][i], visual_prompt='Black and white manga illustration. '+descriptions[index][i],
                                    shot='wide' if i in (0, 7) else ('close' if i in (2, 4, 6) else 'medium'),
                                    emphasis='splash' if i == 0 else ('wide' if i == 5 else 'normal'),
                                    characters=[mara, ivo] if i in (1, 3, 4, 7) else [], bubbles=bubbles,
                                    caption='Die Stunde, die es nicht geben durfte.' if i == 0 else ''))
            paragraph = min(s, len(source)-1)
            scenes.append(Scene(title=f'Szene {s+1}', location='Alte Station', source_start=paragraph+1,
                                source_end=paragraph+1, source_excerpt=source[paragraph][:90], panels=panels).model_dump())
        chapter.update(scenes=scenes, summary='Mara folgt einer unmöglichen Spur in einer verlassenen Bahnstation.', revision=1)
        store.write('chapters', chapter, project['id'], chapter['position'])
    return project
