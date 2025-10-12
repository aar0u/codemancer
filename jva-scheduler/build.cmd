set PATH=%JAVA_HOME%\bin
javac JvaScheduler.java
jar cvfe JvaScheduler.jar JvaScheduler *.class
del *.class
