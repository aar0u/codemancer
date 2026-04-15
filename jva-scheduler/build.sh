#!/bin/bash

javac *.java
jar cvfe jvaScheduler.jar JvaScheduler *.class
rm -f *.class

echo "Build completed successfully!"
