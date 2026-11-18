"""Read-only provider health (one call per provider, never prints a key). Run: docker exec -i orm_dashboard-backend-1 python3 - < scripts/provider_health.py"""
import os, json, time, urllib.request, urllib.error, datetime
def get(url, headers=None, t=20):
    t0=time.time()
    try:
        r=urllib.request.urlopen(urllib.request.Request(url,headers=headers or {"User-Agent":"Mozilla/5.0"}),timeout=t)
        b=r.read(); return r.status,len(b),round(time.time()-t0,2),b[:0]
    except urllib.error.HTTPError as e:
        b=e.read(); return e.code,len(b),round(time.time()-t0,2),b[:150]
    except Exception as e:
        return type(e).__name__,0,round(time.time()-t0,2),b""
out={"utc":datetime.datetime.utcnow().isoformat()}
out["google_news"]=get("https://news.google.com/rss/search?q=Nykaa&hl=en-IN&gl=IN&ceid=IN:en")[:3]
out["gdelt"]=get("https://api.gdeltproject.org/api/v2/doc/doc?query=Nykaa&mode=artlist&maxrecords=1&format=json")[:3]
out["hn_algolia"]=get("https://hn.algolia.com/api/v1/search?query=Nykaa&hitsPerPage=1")[:3]
k=os.environ.get("APIFY_API_TOKEN")
out["apify"]=get("https://api.apify.com/v2/users/me",{"Authorization":"Bearer "+k})[:3] if k else "KEY_MISSING"
k=os.environ.get("OPENROUTER_API_KEY")
out["openrouter"]=get("https://openrouter.ai/api/v1/auth/key",{"Authorization":"Bearer "+k})[:3] if k else "KEY_MISSING"
out["youtube_key_present"]=bool(os.environ.get("YOUTUBE_API_KEY"))
try:
    from app.adapters import youtube as yt
    used=int(yt.redis_client.get(yt._quota_key()) or 0)
    out["youtube_units_used_today"]=used; out["youtube_key"]=yt._quota_key(); out["youtube_remaining_of_10000"]=10000-used; out["backfill_headroom_to_4000"]=max(0,4000-used)
except Exception as e: out["youtube_err"]=repr(e)
from app.core.config import settings
for n in ("BOLSTER_API_KEY","WHOISFREAKS_API_KEY","REALITY_DEFENDER_API_KEY"):
    out[n.lower()+"_present"]=bool(getattr(settings,n,None))
print(json.dumps(out,indent=1,default=str))
