#!/usr/bin/env python3
"""Build a screened Hamilton map-layer release from local GeoJSON snapshots.

Raw source files stay outside this repository. Example:
  python3 scripts/build_hamilton_map_layers.py \\
    --input-root /path/to/local-data \\
    --basemap /path/to/hamilton-20261116.pmtiles \\
    --output releases/map/ca-on-hamilton/2026-11-16-layer-set-001
Requires tippecanoe 2.53.0. The generated release is immutable once published.
"""
from __future__ import annotations
import argparse, hashlib, json, os, pathlib, shutil, subprocess, tempfile

SOURCES = {
 'zoning': ('hamilton-city/zoning-bylaw-boundary-hamilton-2026-10-17/zoning-bylaw-boundary.geojson', ['ZONING_CODE','ZONING_DESC','COMMUNITY','URBAN_RURAL_SETTLE','BY_LAW_NUMBER','EXCEPTION1','EXCEPTION2','EXCEPTION3','HOLDING1','HOLDING2','HOLDING3'], 'City of Hamilton', 'https://open.hamilton.ca/', 11829, 8, 14, 'planning', '#bd663e'),
 'secondary-plan-land-use': ('hamilton-city/secondary-plan-land-use-hamilton-2026-10-17/secondary-plan-land-use.geojson', ['LANDUSE_CLASS','SEC_PLAN_NAME','COMMUNITY','AREA_HEC'], 'City of Hamilton', 'https://open.hamilton.ca/', 47206, 8, 14, 'planning', '#8b6ca8'),
 'urban-boundary': ('hamilton-city/urban-boundary-hamilton-2026-10-17/urban-boundary.geojson', [], 'City of Hamilton', 'https://open.hamilton.ca/', 1, 6, 14, 'planning', '#245e6b'),
 'rural-boundary': ('hamilton-city/rural-boundary-hamilton-2026-10-17/rural-boundary.geojson', [], 'City of Hamilton', 'https://open.hamilton.ca/', 1, 6, 14, 'planning', '#497453'),
 'employment-lands': ('hamilton-city/employment-lands-hamilton-2026-10-17/employment-lands.geojson', ['AREA_NAME','CATEGORY','AREA_HECTARES'], 'City of Hamilton', 'https://open.hamilton.ca/', 22, 6, 14, 'planning', '#e0a02d'),
 'greenbelt': ('lio/greenbelt-designation-hamilton-2026-10-17/greenbelt-designation.geojson', ['DESIGNATION'], 'Ontario Land Information Ontario', 'https://geohub.lio.gov.on.ca/', 9, 6, 13, 'protected', '#4d8963'),
 'niagara-escarpment-plan': ('lio/nep-designation-hamilton-2026-10-17/nep-designation.geojson', ['DESIGNATION'], 'Ontario Land Information Ontario', 'https://geohub.lio.gov.on.ca/', 115, 6, 13, 'protected', '#3f7373'),
 'conservation-hca': ('hca/regulated-areas-hamilton-2026-10-17/regulated-areas.geojson', [], 'Hamilton Conservation Authority', 'https://hca-open-data-camaps.hub.arcgis.com/', 134, 6, 13, 'protected', '#4e7bb4'),
 'conservation-npca': ('npca/approximate-regulation-lands-hamilton-2026-10-17/approximate-regulation-lands.geojson', [], 'Niagara Peninsula Conservation Authority', 'https://gis-npca-camaps.opendata.arcgis.com/', 271, 6, 13, 'protected', '#4e7bb4'),
 'conservation-grca': ('grca/regulation-limits-hamilton-2026-10-17/grca_regulation_limits_hamilton_clipped.geojson', ['GR_FEATURE','MU_LTIER','MU_UTIER'], 'Grand River Conservation Authority', 'https://data.grandriver.ca/downloads-geospatial.html', 199, 6, 13, 'protected', '#4e7bb4'),
 'parks': ('hamilton-city/parks-hamilton-2026-10-17/parks.geojson', ['NAME','PARK_CLASS','TYPE','AREA_HA'], 'City of Hamilton', 'https://open.hamilton.ca/', 633, 8, 14, 'parks', '#398257'),
}
LABELS = {
 'zoning':'Zoning by-law', 'secondary-plan-land-use':'Secondary plan land use',
 'urban-boundary':'Urban boundary', 'rural-boundary':'Rural boundary',
 'employment-lands':'Employment lands', 'greenbelt':'Greenbelt',
 'niagara-escarpment-plan':'Niagara Escarpment Plan designation',
 'conservation-hca':'Conservation area · Hamilton Conservation Authority',
 'conservation-npca':'Conservation area · Niagara Peninsula Conservation Authority',
 'conservation-grca':'Conservation area · Grand River Conservation Authority',
 'parks':'Parks',
}

def sha256(path: pathlib.Path) -> str:
    h=hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda:f.read(1024*1024),b''): h.update(block)
    return h.hexdigest()

def write_json(path: pathlib.Path, data: object) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')

def main() -> None:
    ap=argparse.ArgumentParser()
    ap.add_argument('--input-root',required=True,type=pathlib.Path)
    ap.add_argument('--basemap',required=True,type=pathlib.Path)
    ap.add_argument('--output',required=True,type=pathlib.Path)
    ap.add_argument('--tippecanoe',default='tippecanoe')
    args=ap.parse_args()
    root=args.input_root.resolve(); basemap=args.basemap.resolve(); output=args.output.resolve()
    executable=pathlib.Path(args.tippecanoe).expanduser()
    env=os.environ.copy()
    if executable.is_absolute():
        env['PATH']=str(executable.parent)+os.pathsep+env.get('PATH','')
    tippecanoe=executable.name
    if output.exists() and any(output.iterdir()): raise SystemExit('output must be empty; releases are immutable')
    output.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='hm-map-tiles-') as temp:
        work=pathlib.Path(temp); prep=work/'prep'; prep.mkdir(); (work/'tmp').mkdir()
        observed={}; layer_docs=[]
        for layer,(relative,fields,source,source_url,expected,zmin,zmax,group,color) in SOURCES.items():
            src=root/relative; doc=json.loads(src.read_text(encoding='utf-8')); features=doc.get('features',[]); rows=0; null_geometry=0
            target=prep/(layer+'.ndjson')
            with target.open('w',encoding='utf-8') as out:
                for feature in features:
                    geometry=feature.get('geometry'); props=feature.get('properties') or {}
                    if geometry is None: null_geometry+=1; continue
                    clean={key:props[key] for key in fields if props.get(key) not in (None,'',' ')}
                    out.write(json.dumps({'type':'Feature','properties':clean,'geometry':geometry},separators=(',',':'),ensure_ascii=False)+'\n'); rows+=1
            if rows != expected: raise SystemExit(f'{layer}: expected {expected} mapped features, observed {rows}')
            observed[layer]={'path':relative,'sha256':sha256(src),'source_feature_count':len(features),'mapped_feature_count':rows,'null_geometry_skipped':null_geometry,'fields':fields,'source':source,'source_url':source_url}
            layer_docs.append({'id':layer,'label':LABELS[layer],'source':source,'source_url':source_url,'source_date':'2026-10-17','clearance':'Public dataset; explicitly cleared by project owner for this release.','tile_layer':layer,'feature_count':rows,'min_zoom':zmin,'max_zoom':zmax,'file':f'tiles/{group}.pmtiles','color':color,'default_visible':False,'properties':fields,'group':group})
        version_result=subprocess.run([tippecanoe,'--version'],cwd=work,env=env,text=True,capture_output=True,check=True)
        version=(version_result.stdout+version_result.stderr).strip()
        if version!='tippecanoe v2.53.0': raise SystemExit(f'expected tippecanoe v2.53.0, got {version}')
        commands=[]
        for group,names,zmax in [('planning',[n for n,x in SOURCES.items() if x[7]=='planning'],14),('protected',[n for n,x in SOURCES.items() if x[7]=='protected'],13),('parks',['parks'],14)]:
            output_file=f'{group}.pmtiles'
            cmd=[tippecanoe,'--force','--read-parallel','--temporary-directory=tmp','--no-progress-indicator','-o',output_file,'-n',f'Hamilton {group} map layers','-Z','6','-z',str(zmax),'--detect-shared-borders','--simplification=3','--drop-densest-as-needed','--extend-zooms-if-still-dropping']
            for name in names: cmd += ['-L',f'{name}:prep/{name}.ndjson']
            subprocess.run(cmd,cwd=work,env=env,check=True)
            dest=output/'tiles'/output_file; dest.parent.mkdir(parents=True,exist_ok=True); shutil.copy2(work/output_file,dest)
            commands.append({'argv':cmd,'cwd':'temporary build directory'})
        (output/'basemap').mkdir(parents=True,exist_ok=True)
        shutil.copy2(basemap,output/'basemap'/'hamilton-20261116.pmtiles')
    layers=layer_docs
    manifest={'schema':1,'release':{'unit':'ca-on-hamilton-map-layers','id':'2026-11-16-layer-set-001'},'jurisdiction':'Hamilton, Ontario, Canada','generated_at':'2026-11-16','generator':version,'layers':layers,'basemap':{'file':'basemap/hamilton-20261116.pmtiles','bytes':basemap.stat().st_size,'sha256':sha256(basemap),'max_zoom':15,'source':'Protomaps daily build 2026-11-16; OpenStreetMap and Natural Earth','attribution':'© OpenStreetMap','license':'Open Database License (ODbL) 1.0'},'notes':['Map overlays show thematic source features, not parcel-level joins or legal determinations.','Parks are source features and have not been joined to parcel records.','Only the fields listed in each layer properties allowlist are present in tiles.']}
    write_json(output/'manifest.json',manifest)
    write_json(output/'basemap.json',{'file':manifest['basemap']['file'],'max_zoom':15,'attribution':'© OpenStreetMap'})
    write_json(output/'provenance'/'sources.json',{'schema':1,'snapshot_date':'2026-10-17','sources':list(observed.values()),'basemap':manifest['basemap']})
    write_json(output/'provenance'/'build.json',{'schema':1,'code':'scripts/build_hamilton_map_layers.py','generator':version,'build_commands':commands,'grouping':{'planning':'zoning, secondary-plan-land-use, urban-boundary, rural-boundary, employment-lands','protected':'greenbelt, niagara-escarpment-plan, conservation-hca, conservation-npca, conservation-grca','parks':'parks'},'tile_processing':'GeoJSON EPSG:4326; property allowlists; tippecanoe shared-border detection; simplification 3; density dropping if required; zoom extension if required','source_hashes':observed})
    files=[]
    for path in sorted(p for p in output.rglob('*') if p.is_file() and p.name!='files.json'):
        files.append({'path':path.relative_to(output).as_posix(),'bytes':path.stat().st_size,'sha256':sha256(path)})
    write_json(output/'files.json',{'schema':1,'files':files})
    print(f'Built {len(layers)} layers, {len(files)} release files, {sum(f["bytes"] for f in files)} bytes')
if __name__=='__main__': main()
