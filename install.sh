#!/bin/sh

if [[ $EUID -ne 0 ]]; then
	echo "Cannot install without root priviledges, please use sudo" 1>&2
	exit 1
fi

# Not all systems store manpages in the same place, so we may eventually
# want to use more complex logic for determining that path.
DIR=`dirname $0`
cp -v $DIR/torhost.py /usr/local/bin/torhost
cp -v $DIR/torhost.1 /usr/local/man/man1/torhost.1
