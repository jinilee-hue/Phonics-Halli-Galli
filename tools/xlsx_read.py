import zipfile, xml.etree.ElementTree as ET, re
NS={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
R='{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
def col2n(c):
    n=0
    for ch in re.match(r'[A-Z]+',c).group(): n=n*26+ord(ch)-64
    return n-1
def sheet(f,name):
    z=zipfile.ZipFile(f)
    try:
        x=ET.fromstring(z.read('xl/sharedStrings.xml'))
        ss=[''.join(t.text or '' for t in si.iter('{%s}t'%NS['m'])) for si in x.findall('m:si',NS)]
    except KeyError: ss=[]
    wb=ET.fromstring(z.read('xl/workbook.xml'))
    rmap={r.get('Id'):r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
    for s in wb.find('m:sheets',NS):
        if s.get('name')==name:
            t=rmap[s.get(R)].lstrip('/'); t=t if t.startswith('xl/') else 'xl/'+t
            sx=ET.fromstring(z.read(t)); out=[]
            for r in sx.findall('.//m:sheetData/m:row',NS):
                row={}
                for c in r.findall('m:c',NS):
                    tp=c.get('t'); v=c.find('m:v',NS)
                    if tp=='s' and v is not None: val=ss[int(v.text)]
                    elif tp=='inlineStr': val=''.join(x.text or '' for x in c.iter('{%s}t'%NS['m']))
                    elif v is not None: val=v.text
                    else: val=''
                    row[col2n(c.get('r'))]=val
                if row: out.append([row.get(i,'') for i in range(max(row)+1)])
            return out
