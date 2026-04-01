#!/bin/bash
cd /home/beast/projects/hyperretrieval/research
echo "Serving HyperRetrieval Research Dashboard at http://localhost:8004/dashboard.html"
python3 -m http.server 8004
