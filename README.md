TorHost
=======

TorHost aims to make hosting files on Tor trivial. It's as easy as:

    torhost foo

Then wait while TorHost fires up Tor, connects to the network, generates a hidden service, hosts 'foo' on the hidden service, and prints out the onion address for users to download from. That's it.

Options
-------

    Options:
      -h, --help            show this help message and exit
      -p PORT, --port=PORT  Specify port to host hidden service on (default: 80)
      -k, --keepalive       Upload file to multiple users instead of one
      -d, --debug           Enable debugging information

Requirements
------------

TorHost uses Ephemeral Hidden Services, a relatively new feature of Tor. It therefore requires (at a minimum) Stem 1.4, and Tor 0.2.7.1-alpha or better. All other dependencies should have come with Python.
