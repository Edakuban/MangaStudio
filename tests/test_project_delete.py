import copy
import pytest
from fastapi.testclient import TestClient
from mangastudio.web import create_app


@pytest.fixture
def setup(tmp_path):
    with TestClient(create_app(tmp_path/'data',start_worker=False)) as client:
        p=client.post('/api/demo').json()
        yield client,client.app.state.store,p


def test_delete_and_restore_keep_whole_book_and_assets(setup):
    client,store,p=setup;pid=p['id']
    before=copy.deepcopy(client.get('/api/projects/'+pid).json())
    chapters=store.list('chapters',pid);chars=store.list('characters',pid)
    file=store.asset(f'books/{pid}/test-preserved.png');file.parent.mkdir(parents=True,exist_ok=True);file.write_bytes(b'original asset')
    assert client.delete('/api/projects/'+pid).status_code==200
    assert not client.get('/api/projects').json()
    assert client.get('/api/projects/'+pid).status_code==404
    assert client.get('/api/chapters/'+chapters[0]['id']).status_code==404
    deleted=client.get('/api/deleted-projects').json();assert [x['id'] for x in deleted]==[pid]
    assert store.list('chapters',pid)==chapters and store.list('characters',pid)==chars
    assert file.read_bytes()==b'original asset'
    assert client.post('/api/projects/'+pid+'/style-analysis').status_code==404
    assert client.post('/api/projects/'+pid+'/restore').status_code==200
    assert client.get('/api/projects/'+pid).json()==before
    assert not client.get('/api/deleted-projects').json()


def test_busy_project_cannot_be_deleted_or_restored(setup):
    client,store,p=setup;pid=p['id'];job=store.enqueue(pid,None,'book_style',{})
    assert client.delete('/api/projects/'+pid).status_code==400
    assert client.get('/api/projects/'+pid).status_code==200
    assert client.post('/api/projects/'+pid+'/restore').status_code==400
    store.update_job(job,state='failed')
    assert client.delete('/api/projects/'+pid).status_code==200
    assert client.post('/api/jobs/'+job+'/retry').status_code==404
    with pytest.raises(KeyError):store.enqueue(pid,None,'book_style',{})
    assert client.post('/api/projects/'+pid+'/restore').status_code==200


def test_unknown_project_delete_and_restore_return_404(setup):
    client,store,p=setup
    assert client.delete('/api/projects/'+'f'*32).status_code==404
    assert client.post('/api/projects/'+'f'*32+'/restore').status_code==404
    assert len(client.get('/api/projects').json())==1
