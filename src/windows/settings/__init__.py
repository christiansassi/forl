"""What the widget remembers between runs, and how it acts on it.

Two things survive a restart: which usages of each service the user chose to
show, in the order they chose them, and whether the widget should start with the
machine. Both are stored here and nowhere else.

Storing is all this package does. A preference that has to be carried out, such
as starting with the machine, is applied by the platform backend under
src/windows/system, because how it is done differs by machine while what was
chosen does not.

Everything is kept in one file: a section per service for its selection, and one
general section for what belongs to the widget as a whole.
"""
