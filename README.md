# spotifeed-py

Original version https://github.com/timdorr/spotifeed rewritten with python to allow:
* All podcast markets (original only US)
* All podcast episode (previously limited to 50 most recent)


## How to run:
Set Environment vars:

FLASK_APP=main.py

SPOTIPY_CLIENT_ID=<SPOTIFY_CLIENT_ID>

SPOTIPY_CLIENT_SECRET=<SPOTIFY_CLIENT_SECRET>

RUN:

python3 flask run --host=(ip) --port=(port)
