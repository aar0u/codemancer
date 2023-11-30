set PATH=%JAVA_HOME%\bin
javac ActionDemo.java
jar cvfe ActionDemo.jar ActionDemo *.class
del *.class
