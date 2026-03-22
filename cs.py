import json
data = json.load(open("/home/beast/projects/mindmap/pipeline/output/graph_with_summaries.json"))
summaries = data.get("cluster_summaries", {})
good = {k: v for k, v in summaries.items() if not v.get("name","").startswith("cluster_")}
bad  = {k: v for k, v in summaries.items() if v.get("name","").startswith("cluster_")}
print("Total:", len(summaries), " Good:", len(good), " Failed:", len(bad))
for k, v in bad.items():
    print("  FAILED cluster_" + k + " ->", v.get("purpose","?"))
