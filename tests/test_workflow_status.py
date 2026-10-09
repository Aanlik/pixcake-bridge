from sqlalchemy import select, create_engine, inspect
from pixcake_bridge.models import Photo, Project, database
from test_engine import setup


async def test_later_selections_survive_restart_and_cancellation(tmp_path):
    engine, client, cfg, db = setup(tmp_path, 2)
    client.rows[1]['color_label'] = None
    await engine.sync()
    engine.set_stage(7, 'EDITING')
    client.rows[1]['color_label'] = 'green'
    await engine.sync()
    with engine.sessions() as s:
        assert not s.scalar(select(Photo).where(Photo.photo_id == 1)).added_during_editing
        assert s.scalar(select(Photo).where(Photo.photo_id == 2)).added_during_editing
    client.rows[1]['color_label'] = None
    await engine.sync()
    db.dispose()
    db, sessions = database(cfg.database_url)
    with sessions() as s:
        p = s.scalar(select(Photo).where(Photo.photo_id == 2))
        assert p.added_during_editing and p.cancelled and p.selected_path
    db.dispose()


def test_upgrade_old_sqlite_preserves_photos(tmp_path):
    url = 'sqlite:///' + str(tmp_path / 'old.db')
    db = create_engine(url)
    with db.begin() as c:
        c.exec_driver_sql('CREATE TABLE photos (id INTEGER PRIMARY KEY, project_id INTEGER, photo_id INTEGER, source_filename TEXT)')
        c.exec_driver_sql("INSERT INTO photos VALUES (1,1,10,'DSC00001.JPG')")
    db.dispose()
    db, _ = database(url)
    assert 'added_during_editing' in {x['name'] for x in inspect(db).get_columns('photos')}
    with db.connect() as c:
        assert c.exec_driver_sql('SELECT source_filename, added_during_editing FROM photos').one() == ('DSC00001.JPG', 0)
    db.dispose()


def test_archive_restore_returns_project_to_saved_stage(tmp_path):
    engine, _client, _cfg, db = setup(tmp_path)
    engine.set_stage(7, 'EDITING')
    engine.set_stage(7, 'ARCHIVED')

    assert engine.restore_stage(7) == 'EDITING'
    with engine.sessions() as s:
        project = s.scalar(select(Project).where(Project.event_id == 7))
        assert project.stage == 'EDITING'
        assert project.previous_stage is None
        assert project.has_entered_editing
    db.dispose()
