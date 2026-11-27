This folder contains some example sessions you may verify with the public key committed to keys/

The session used contains some text to speech voice.

Usage:

run python setup.py

run python lpat.py verify example-sessions\intact --public-key example-sessions\public_key.pem<br>
    - Should print out a successful verification with the result "INTACT"

run python lpat.py verify example-sessions\new-file --public-key example-sessions\public_key.pem<br>
    - Should print out "MODIFIED" and tell you that a new file boo.txt has been added.

More examples are available in the same directory that can be tested the same way.