#!/bin/bash
set -e

if [[ $# -ne 1 ]]; then
    echo "Usage: $0 <output_jar>"
    exit 1
fi

output_jar="$1"

javac *.java
for classfile in *.class; do
    class=$(basename "$classfile" .class)
    if javap "$class" | grep -q 'public static void main(java.lang.String\[\])'; then
        echo "Found main: $class" >2
    fi
done
jar cf $output_jar *.class
