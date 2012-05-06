wsconfig
========

This is a small utility I am using to auto-configure my workstations:
Installing packages, linking dotfiles etc.

Design goals (aka "why not a shell script?"):

- Provide a tagging system to select which commands to run on a particular
  system.

- Provide high-level commands, so the same script may on different operating
  systems with less duplication.

- Simplify certain things, like symlinking: ``ln`` on Linux requires knowledge
  of the relative path between target and source.

I put my wsconfig script together with my dotfiles and even some binaries
in Dropbox.


Language
--------

Put each command on it's own line::

    mkdir ~/bla
    link vimrc ~/.vimrc
    $ echo 'hello world' >> /tmp/test

``mkdir`` and ``link`` are high-level commands implemented in Python. ``$`` is
run directly in the shell. See further below for all commands.

To restrict commands to a specific operating system::

    sys:osx {
       $ defaults write NSGlobalDomain AppleShowScrollBars -string "Always"
    }


The list of predefined tags on the current system can be displayed by running
``wsconfig --defaults``. Tags that you might see there are ``sys:windows``,
``sys:linux``, ``sys:macos``, but also ``sys:ubuntu``, ``sys:ubuntu:natty``
or ``sys:windows:7``.

Custom tags can be used::

    DevEnvironment {
        dpkg python-setuptools
    }


Because the tag in the above example starts with an uppercase letter,
``wsconfig`` will consider it "public" and present it to you as a choice to
define on the command line. You can use lowercase tags internally to split
commands into blocks::

    DevEnvironment {
        define php
        define python
    }

    python {
        dpkg python-setuptools
        $ easy_install pip
    }

    php {
        dpkg php5-cli php5-xdebug
    }

At this point it is worth pointing out that even though ``php`` and ``python``
above appears to  look like "packages" of some sort, thinking about them in
thta way is not correct. They are really "if conditions", and the commands are
guaranteed to run in the order they appear in the script file - i.e., first
the commands in the ``python`` block, then those in the ``php`` block.

However, you can think of ``DevEnvironment`` as a package, because the
``define`` directives are special, processed in a separate pass, and must not
be combined with other commands. i.e. the  following are both not valid::


    tag {
        define foo
        dpkg screen
    }
    tag {
        define foo
        subtag { }
    }


Yes, that's right, you can nest conditions::

    python {
        sys:linux { dpkg: python-setuptools }
        sys:osx { $ brew install python-setuptools }
    }


A condition can also specify multiple tags. The following is the exact
equivalent to the above. What you prefer is a matter of style::

    python sys:linux { dpkg: python-setuptools }
    python sys:osx { $ brew install python-setuptools }


If you combine a capitalized tag with a system tag, the capitalized tag will
only be offered as choice when running on that system::

    sys:linux VirtualMachine {
        $ gconftool-2 -s /apps/gnome-screensaver/lock_enabled --type=bool false
    }

When running the above on Windows, ``wsconfig`` is smart enough to realize
that there are no commands backing the ``VirtualMachine`` tag, and will
ignore it.

Nested conditions, and tags combined with whitespace or both treated as ``AND``.
You can als do ``OR``, by using a comma::

    sys.linux, sys.osx { link: ssh/config ~/.ssh/config }


``AND`` and ``OR`` can be combined (but complex expressions using brackets
are currently not supported)::

    sys.linux, sys.windows Cygwin {
        define tarsnap
    }

Above, the tag ``tarsnap`` will only be defined if we're on Linux, or if we're
on Windows *and* the ``Cygwin`` tag has been selected (remember, since it's
uppercase, the user will be presented ``Cygwin`` as a choice).


Root usage
----------

You'll want to run some commands as root, but usually not all - you want your
config files to be created with you as the owner. ``wsconfig`` uses ``sudo``
to run commands as root.

Some commands, like ``dpkg``, use sudo by default. Others, like ``link`` or
``mkdir``, to run them as root, you can prefix them with the term ``sudo``::

    sudo mkdir /opt/foo

For shell commands, you are free to do whatever you like, since they will be
piped directly to the shell::

    $ sudo apt-get update
    $ su -c "apt-get update"


Tagging limitations
-------------------

There are some limitations to the tagging system.

The following is not allowed::

    DevEnviron {
        define python
    }
    python {
        Python3 {}
    }

Neither is this::

    Dev {
        Python {}
        Php {}
    }

The reason is that in both cases a capitalized tag is used which is not on
the root level. This is a dilemma - ``wsconfig`` would either have to
indiscriminately present all such tags as choices, even though, in the last
example, defining ``Python`` has no effect without also defining ``Dev``. Or
it would have to present you with a tree of choices, i.e. recognizing the
dependency between ``Dev`` and ``Python``, or implement a multi-step choice
system. While possible, it doesn't do this currently.

Instead, you have to use something like this::

    Dev {
        define Dev-PHP
        define Dev-Python
    }

    Dev-PHP {}
    Dev-Python {}


Available plugins
-----------------

$
    Execute something in the shell. These are not parsed like other commands -
    instead, content is given to the shell as-is.

dpkg
    Install dpkg packages on Debian-systems, using apt-get.

link
    Create a symbolic link. Both pathnames can be relative to the config
    file itself, wsconfig will properly construct the link target path.

    The command will fail if the target file already exists with a different
    link target than the one you wish to say. You can add an ``-f`` option
    to force a link overwrite::

        link -f virtualenvs/postmkvirtualenv ~/.virtualenvs/postmkvirtualenv

mkdir
    Creates a directory, if it does't exist yet.

pip
    Install a Python package using "pip". pip needs to be available.

wine
    Run a windows executable via wine.

remind
    Remind yourself of some manual setup step. These will be collected and
    presented at the end of the script.


Applying a config file:
----------------------

::

    $ wsconfig my_config_file
    Available choices:
      Dev
      Vm
    $ wsconfig my_config_file apply Development

    
    
Similar tools
-------------

https://github.com/technicalpickles/homesick
