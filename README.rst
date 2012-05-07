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

What's more, the ``define`` statements are executed sequentially as well, thus
the following will not be want you want, because the ``define`` appears to late
to have any actual effect::

    php {
        dpkg php5-cli
    }
    DevEnvironment {
        define php
    }


You can nest conditions::

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

Tags can also be negated. If you want to install Thunderbird only when not in
a virtualized environment::

    sys:linux !Vm {
        dpkg thunderbird
    }

Finally, you can also use comments, of course:

    # To fix monospace fonts in Java apps
    # https//bugs.launchpad.net/ubuntu/+source/sun-java6/+bug/569396
    dpkg ttf-dejavu

There is no syntax for multiline comments, but if you're paying attention,
there's an obvious way to implement them: Use a tag selector to disable a
block of statements::

    comment {
    sys:linux (
        ...
    }
    }



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


Tagging in-depth
----------------

Here are some extended thoughts on the tagging system, and my thinking about
it (currently still an ongoing process).

Initially, the ``define`` command was considered out-of-sequence. It was being
preprocessed such that the following worked as expected::

    foo bar qux { remind "Stop drinking" }
    bar { define qux }
    foo { define bar }
    define foo

We would traverse the document until no new ``defines`` are activated, and then
use all discovered tags as the starting set. However, this seemed kid of
schizophrenic. The inclination would be to use it like this::

    sys.linux {
        ...
        foo
        ...

        define chrome

        ...
    }

I.e., as a sort of "call" or "include", with the ``chrome`` selector serving
to encapsulate the relevant commands visually/structurally. And while the above
does indeed work, even now, if the ``chrome`` block comes after it, the whole
point of this being supposed to be an include is that it shouldn't matter where
in the file it is located.
But that's not really what ``define`` is. If above the ``foo`` command fails,
and the script is aborted at this point, you'd expect a ``chrome`` block to not
be processed. However, if ``defines`` are preprocessed as was the case, then
such a block might have already run.

So to combat that, I wanted to add restrictions on ``define``, such that they
may only be used in selectors that have no other commands::

    sys:linux {
        define base-linux
        define foo
    }
    Development {
        define base-development
        define python
        define php
    }


It would be an artificial restriction intended to make things clearer, but as
you can see, it leads to an entirely different style of writing config files.
You'd be forced to put ALL commands within faux selectors (like ``base-linux``),
which is ugly, while at best making the problem, that here is no longer a
clear order of execution, only somewhat more bearable (if the above looks clear,
think about a large file with sequential commands being intermixed with such
packages.

It just doesn't make sense to encourage using ``define`` as an inclusion
concept, which is what preprocessing them in this way does. It's schizophrenic
because it is confused about whether tag selectors are what the claim to be,
"if conditions", or whether they should be viewed as "packages".

Instead, if needed, a package concept could be introduced separately::

    @chrome (
        ...
    )

    sys:linux {
        ....
        @chrome  # Include the chrome package.
    }

The @()-syntax could indicate a package, NOT a selector, and they would only
ever run when included (but only once). These could also have other uses, like
indicating a "unit of execution", where errors would be caught, such that an
error in the package causes subsequent statements in the package to be skipped,
but further statements outside to be run.

On the other hand, introducing a different type of syntax might already be too
much. This is supposed to be simple after all. There is another potential
solution: A multi-pass apply process. So if we take the example from before::

    sys.linux {
        ...
        foo
        ...

        define chrome
        ...
    }

Then ``chrome`` would not be preprocessed. If the script ends with ``foo``,
then no ``chrome`` block will have run. Instead, code processing the document
comes across the ``define`` only when ``foo`` has already run, and when it
does, it schedules another document traverse. The second time, commands that
have already run skipped, but commands newly unlocked by the tag are run now.

This might be the perfect solution because:
    - No extra syntax.
    - The order in which commands run is not any more confusing then with @(),
      and it could be used equally as effectively to structure code.
    - It avoids the main conceptional issue with the original ``define`` -
      that it was processed out-of-order.
    - The @() syntax would need to implement code to avoid running multiple
      times as well.
    - It fixes the problem that defines have now, that they have no effect
      if in the wrong order.

----


There's a further aspect that I'm currently not happy with. Take the following
pieces of code::

    DevEnviron {
        Python {}
        Php {}
    }

::

    DevEnviron {
        define python
    }
    python {
        Python3 {}
    }

In both cases, only the ``DevEnviron`` tag will be presented as a choice.
Why? ``wsconfig`` would either have to indiscriminately present all such tags
as choices, as a flat list, without recognizing the dependencies, even though,
in the first example, defining ``Python`` has no effect without also defining
``DevEnviron`` (this could be an optional ``--all`` switch).
Or it would have to present you with a tree of choices, i.e. recognizing the
dependency between ``Dev`` and ``Python``. This could happen through a smart
algorithm, or by going through a multi-step choice process (choose
``DevEnviron``, then choose ``Python``, after each step traversing the tree for
new tags that become available).

Initially, I thought about validation rules that prevented such tags from being
``hidden``, but that doesn't really make a lot of sense, and one reason is how
easy it can be worked around. If this fails validation::

    Python {
        Dev {}
    }

Then this would bypass it, but have the same effect (the Python tag being
useless without the Dev tag)::

    Dev {
        python { noop }
    }
    Python { define python }



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
