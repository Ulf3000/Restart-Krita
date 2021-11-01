from .restart import Restart

# And add the extension to Krita's list of extensions:
app = Krita.instance()
# Instantiate your class:
extension = Restart(parent=app)
app.addExtension(extension)