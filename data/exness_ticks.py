"""Exness public historical tick-data loader. No MT4/MT5 and no account login."""
from __future__ import annotations
import csv, io, zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

DEFAULT_BASE = "https://ticks.ex2archive.com/ticks"

class ExnessTickData:
    def __init__(self, cache_dir="data/exness_cache", base_url=DEFAULT_BASE):
        self.cache=Path(cache_dir)
        self.cache.mkdir(parents=True,exist_ok=True)
        self.base_url=base_url.rstrip("/")

    def download_month(self,symbol,year,month):
        dest=self.cache/f"Exness_{symbol}_{year}_{month:02d}.zip"
        if dest.exists() and dest.stat().st_size: return dest
        url=f"{self.base_url}/{symbol}/{year}/{month:02d}/Exness_{symbol}_{year}_{month:02d}.zip"
        req=Request(url,headers={"User-Agent":"forex-bot/1.0"})
        with urlopen(req,timeout=120) as r: data=r.read()
        if not data.startswith(b"PK"):
            raise RuntimeError(f"Invalid Exness archive: {url}")
        dest.write_bytes(data)
        return dest

    def _read_zip(self,path):
        with zipfile.ZipFile(path) as z:
            names=[n for n in z.namelist() if n.lower().endswith(".csv")]
            if not names: raise RuntimeError(f"No CSV in {path}")
            with z.open(names[0]) as raw:
                reader=csv.reader(io.TextIOWrapper(raw,encoding="utf-8-sig",errors="replace"))
                header=None
                for row in reader:
                    if header is None:
                        normalized=[x.strip().strip('"').lower() for x in row]
                        if "timestamp" in normalized and "bid" in normalized and "ask" in normalized:
                            header={name:i for i,name in enumerate(normalized)}
                            continue
                        # Some Exness exports omit the provider column.
                        header={"timestamp":2 if len(row)>=5 else 1,
                                "bid":3 if len(row)>=5 else 2,
                                "ask":4 if len(row)>=5 else 3}
                    try:
                        ts=row[header["timestamp"]].strip().replace('"',"")
                        dt=datetime.fromisoformat(ts.replace("Z","+00:00")).astimezone(timezone.utc)
                        yield dt,float(row[header["bid"]]),float(row[header["ask"]])
                    except (ValueError,TypeError,IndexError,KeyError):
                        continue

    def ticks(self,symbol,start_year,start_month,end_year,end_month):
        y,m=start_year,start_month
        while (y,m)<=(end_year,end_month):
            yield from self._read_zip(self.download_month(symbol,y,m))
            m += 1
            if m == 13: y,m=y+1,1

    def bars(self,symbol,start,end,timeframe="1H"):
        mins={"5M":5,"1H":60,"4H":240}.get(timeframe.upper())
        if not mins: raise ValueError("timeframe must be 5M, 1H or 4H")
        start=start.astimezone(timezone.utc); end=end.astimezone(timezone.utc)
        buckets={}
        for ts,bid,ask in self.ticks(symbol,start.year,start.month,end.year,end.month):
            if not(start<=ts<end): continue
            mid=(bid+ask)/2
            key=datetime.fromtimestamp(
                int(ts.timestamp())-int(ts.timestamp())%(mins*60),tz=timezone.utc
            )
            b=buckets.setdefault(key,{
                "time":key.isoformat(),"open":mid,"high":mid,"low":mid,"close":mid,
                "bid_open":bid,"bid_high":bid,"bid_low":bid,"bid_close":bid,
                "ask_open":ask,"ask_high":ask,"ask_low":ask,"ask_close":ask,
                "volume":0,"spread_sum":0.0
            })
            b["high"]=max(b["high"],mid); b["low"]=min(b["low"],mid); b["close"]=mid
            b["bid_high"]=max(b["bid_high"],bid); b["bid_low"]=min(b["bid_low"],bid); b["bid_close"]=bid
            b["ask_high"]=max(b["ask_high"],ask); b["ask_low"]=min(b["ask_low"],ask); b["ask_close"]=ask
            b["spread_sum"] += ask-bid; b["volume"] += 1
        out=[]
        for b in sorted(buckets.values(),key=lambda x:x["time"]):
            b["spread_avg"]=b["spread_sum"]/b["volume"] if b["volume"] else 0.0
            del b["spread_sum"]
            out.append(b)
        return out
