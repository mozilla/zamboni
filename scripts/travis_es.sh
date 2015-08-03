#!/bin/bash

TARGET="/tmp/elasticsearch"

if [ ! -f "$TARGET/elasticsearch-1.6.2/bin/elasticsearch" ]; then
    echo "$TARGET not found.  Building..."
    pushd $TARGET
    wget https://download.elastic.co/elasticsearch/elasticsearch/elasticsearch-1.6.2.tar.gz
    tar xvf elasticsearch-1.6.2.tar.gz
    elasticsearch-1.6.2/bin/plugin -install elasticsearch/elasticsearch-analysis-icu/2.6.0
else
    echo "$TARGET already exists"
fi
