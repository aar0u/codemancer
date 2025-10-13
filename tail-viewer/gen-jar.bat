javac TailViewer.java

if not exist "dist" mkdir dist

jar.exe cvfe dist\TailViewer.jar TailViewer *.class

del *.class
