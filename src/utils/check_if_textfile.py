import pymupdf

doc = pymupdf.open('data/raw_papers/June 2018 QP - Paper 1 (H) Edexcel Physics GCSE.pdf')
txtblocks = 0
imgblocks = 0
docfonts = []

for page in doc:
    t=page.get_text("dict")
    for b in t['blocks']:
        if(b['type']==0):
            txtblocks+=1
        elif(b['type']==1):
            imgblocks+=1

pagefonts = page.get_fonts()
for f in pagefonts:
    if(f[3] not in tuple(docfonts)):
        docfonts.append(f[3])
print("Text Blocks : ", txtblocks)
print("Img Blocks : ", imgblocks)
print("Fonts : ", len(docfonts))
for ft in docfonts:
    print(ft)
doc.close()