import logging
from datetime import datetime, timezone
import re
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import time
from feedgen.feed import FeedGenerator
from flask import Flask, Response, json
from tinydb import TinyDB, Query
from tinydb.storages import MemoryStorage
import threading

db_lock = threading.RLock()
db = TinyDB(storage=MemoryStorage)
UPDATE_INTERVAL = 360
logging.basicConfig(filename='flask_log_{:%Y-%m-%d}.log'.format(datetime.now()),
                            filemode='a',
                            format='%(asctime)s,%(msecs)d %(name)s %(levelname)s %(message)s',
                            datefmt='%H:%M:%S',
                            level=logging.INFO)
logging.getLogger().addHandler(logging.StreamHandler())

auth_manager = SpotifyClientCredentials()
sp = spotipy.Spotify(auth_manager=auth_manager)
app = Flask(__name__, static_url_path='')


@app.route('/dump')
def dump_db():
    dict_list = {}
    with db_lock:
        db_entries = db.all()

    for db_entry in db_entries:
        check_t = time.strftime('%Y-%m-%d %H:%M:%S',  time.localtime(db_entry.get('insert_t') - UPDATE_INTERVAL ))
        show_info = db_entry.get("show_info")
        show_uri = db_entry.get('show_uri')
        dict_list[show_info.get("name")] = {'last_check':check_t,'uri':show_uri}

    return Response(json.dumps(dict_list), mimetype='application/json')

@app.route('/')
def root():
    return app.send_static_file('index.html')


@app.route('/static/<file>')
def static_files(file):
    return app.send_static_file(file)


@app.route('/favicon.ico')
def redirect_fav():
    return static_files('favicon.png')


@app.route('/<show_uri>', defaults={'country_code': "US"})
@app.route('/<show_uri>/<country_code>')
def get_show_rss(show_uri, country_code):
    if not re.search("\A\w{22,22}$", show_uri):
        return "Incorrect URI Format", 404
    if not re.search("[a-zA-Z]{2}", country_code):
        return "Incorrect country_code Format", 404

    doc_id = get_entry(show_uri, country_code)
    entry = db.get(doc_id=doc_id)
    return Response(str.encode(entry.get('rss_str')), mimetype='application/xml')


def generate_rss(show_info, show_uri, country_code):
    fg = FeedGenerator()
    fg.load_extension('podcast')
    fg.description(show_info['description'])
    fg.author({'name': show_info['publisher']})
    fg.title(show_info['name'])
    fg.link({'href': show_info['external_urls']['spotify']})
    fg.id(show_uri)
    fg.image(show_info.get('images')[0]['url'])
    total_episodes = show_info['episodes']['total']
    added_episodes = 0
    while added_episodes != total_episodes:
        episodes = sp.show_episodes(show_id=show_uri, limit=50, offset=added_episodes, market=country_code)
        for episode in episodes['items']:
            ent = fg.add_entry()
            ent.podcast.itunes_duration(int(episode['duration_ms'] / 1000))
            ent.title(episode.get('name'))
            ent.guid(episode['uri'])
            ent.published(datetime.strptime(episode['release_date'], '%Y-%m-%d').replace(tzinfo=timezone.utc))
            ent.description(episode['description'])
            ent.id(episode['uri'])
            ent.enclosure(url=f"https://anon-podcast.scdn.co/{episode['audio_preview_url'].split('/')[-1]}",
                          length=0,
                          type='audio/mpeg')
            added_episodes += 1
    return fg.rss_str().decode('utf-8')


def get_entry(show_uri, country_code):
    with db_lock:
        db_entry = db.get(Query().show_uri == show_uri)

    doc_id = None
    if db_entry:

        if db_entry.get('insert_t') <= int(datetime.now().timestamp()):
            doc_id = update_show(db_entry.doc_id)
        else:
            doc_id = db_entry.doc_id

    if not doc_id:
        doc_id = get_new_entry(show_uri, country_code)

    return doc_id


def get_new_entry(show_uri, country_code):
    show_info = sp.show(show_id=show_uri, market=country_code)

    db_entry = {
        'insert_t': int(datetime.now().timestamp()) + UPDATE_INTERVAL,
        'show_info': show_info,
        'show_uri': show_uri,
        'country_code': country_code,
        'rss_str': generate_rss(show_info, show_uri, country_code)
    }
    with db_lock:
        return db.insert(db_entry)


def update_show(doc_id):
    with db_lock:
        db_info = db.get(doc_id=doc_id)

    db_show_info = db_info.get("show_info")
    show_info = sp.show(show_id=db_info.get('show_uri'), market=db_info.get('country_code'))
    if show_info.get("total_episodes") != db_show_info.get("total_episodes"):
        db_update = {
            'show_info': show_info,
            'insert_t': int(datetime.now().timestamp()) + UPDATE_INTERVAL,
            'rss_str': generate_rss(show_info, db_info.get('show_uri'), db_info.get('country_code'))
        }

        with db_lock:
            db.update(db_update, doc_ids=[doc_id])

    return doc_id
