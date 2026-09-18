"""What the widget remembers between runs, and how it acts on it.

Three things survive a restart: which usages the user chose to show, in the
order they chose them, whether the widget should start with the machine, and
where the provider keeps the sign-in it reads. All three are stored here and
nowhere else.

Storing is all this package does. A preference that has to be carried out, such
as starting with the machine, is applied by the platform backend under
src/system, because how it is done differs by machine while what was chosen does
not.

Preferences are kept per provider in one file, so a machine running both widgets
has one place to look and each instance touches only its own section.
"""
