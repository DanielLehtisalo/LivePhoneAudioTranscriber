# Live Phone Audio Transcriber (LPAT)
![LPAT graphic](assets/graphic.png)
Transcribe audio from a phone in the local network live, without installing any applications on the phone.

Please do not run LPAT without informing everyone present as most jurisdictions require you to get consent for recording from all parties being recorded.

## Running verification on examples
[Read more here](example-sessions/about.md)

## Running the server (Windows)
- Run setup.py
- Run lpat.py

## Goals
- Get live audio from a browser (phones especially) to a server.
- Transcribe the audio live.

## Considerations & possible future improvements
- Anyone on the local network is able to start a session, this should be relatively simple to fix.
- Support for reconnecting to a session.