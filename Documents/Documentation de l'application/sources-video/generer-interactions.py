"""Génère la vidéo documentaire uniquement (Windows, Pillow, FFmpeg, voix française).

Exécution depuis n'importe quel dossier : py -3.14 generer-interactions.py
Les WAV et les segments intermédiaires restent dans scratch/video-agents.
Aucun serveur, courriel ou fichier métier n'est sollicité.
"""
from pathlib import Path
import hashlib
import json
import math
import shutil
import subprocess
import wave
import argparse
import html
import re
import asyncio
from PIL import Image, ImageDraw, ImageFont

SOURCE = Path(__file__).resolve().parent
DOC = SOURCE.parent
ROOT = DOC.parents[1]
WORK = ROOT / 'scratch/video-agents'
OUT = DOC / 'assets/video-agents'
WORK.mkdir(parents=True, exist_ok=True)
OUT.mkdir(parents=True, exist_ok=True)
SCENES = json.loads((SOURCE / 'scenario-agents.json').read_text(encoding='utf-8'))
FFMPEG = shutil.which('ffmpeg')
if not FFMPEG:
    raise SystemExit('FFmpeg doit être disponible dans PATH.')
W, H, FPS = 1280, 720, 15
VOICE = 'fr-FR-VivienneMultilingualNeural'
RATE = '+0%'
FILM = 'interactions'
MP4_NAME = 'interactions-agents.mp4'
PLAYER = 'video-interactions-agents.html'
INK, GREEN, PAPER = '#19362f', '#17634b', '#f7f6ef'
FONTS = Path('C:/Windows/Fonts')
def font(n, bold=False):
    return ImageFont.truetype(str(FONTS / ('segoeuib.ttf' if bold else 'segoeui.ttf')), n)

def wrapped(draw, text, max_width, ft):
    lines = []
    for part in text.split('\n'):
        line = ''
        for word in part.split():
            trial = f'{line} {word}'.strip()
            if line and draw.textlength(trial, font=ft) > max_width:
                lines.append(line)
                line = word
            else:
                line = trial
        lines.append(line)
    return lines

def text(draw, xy, value, size=24, fill=INK, bold=False, width=None, align='left', spacing=6):
    ft = font(size, bold)
    lines = wrapped(draw, value, width, ft) if width else value.split('\n')
    x, y = xy
    for line in lines:
        xx = x - draw.textlength(line, font=ft) / 2 if align == 'center' else x
        draw.text((xx, y), line, font=ft, fill=fill)
        y += size + spacing
    return y

COLORS = {'Leader':'#17634b', 'orchestrateur':'#17634b', 'courrier':'#426e9c', 'données':'#c87842',
          'contrôle':'#77639a', 'rayon':'#3e8581', 'audit-stock':'#b16a50',
          'articles':'#6f8041', 'tendances':'#607ac0', 'sentinelle':'#59736c'}
def color(name):
    return next((v for k, v in COLORS.items() if k in name), '#a76b3f')

def avatar(draw, x, y, name):
    c = color(name)
    draw.ellipse((x-84,y-78,x+84,y+112), fill='#e9eddf')
    if 'sentinelle' in name.lower():
        draw.rounded_rectangle((x-59,y-25,x+59,y+66),18,fill=c)
        draw.rounded_rectangle((x-44,y-13,x+44,y+35),12,fill='#dfedac')
        draw.ellipse((x-28,y+2,x-18,y+12), fill=INK)
        draw.ellipse((x+18,y+2,x+28,y+12), fill=INK)
        draw.line((x,y-25,x,y-50),fill=c,width=5)
        draw.ellipse((x-7,y-64,x+7,y-50),fill='#d57643')
        draw.line((x-24,y+74,x-24,y+97),fill=c,width=8)
        draw.line((x+24,y+74,x+24,y+97),fill=c,width=8)
    elif name.startswith('Logiciel'):
        draw.rounded_rectangle((x-78,y-41,x+78,y+63),14,fill=c)
        draw.rounded_rectangle((x-66,y-29,x+66,y+42),5,fill='#fffdf5')
        draw.line((x,y+64,x,y+86),fill=c,width=8)
        draw.line((x-41,y+90,x+41,y+90),fill=c,width=8)
        text(draw,(x,y-20),'signal',24,c,True,align='center')
        text(draw,(x,y+10),'→ IA',21,c,True,align='center')
    else:
        draw.rounded_rectangle((x-51,y+15,x+51,y+100),26,fill=c)
        draw.polygon([(x-14,y+14),(x+14,y+14),(x,y+43)],fill='#fffdf5')
        draw.rounded_rectangle((x-11,y-1,x+11,y+25),8,fill='#dbab83')
        draw.ellipse((x-37,y-67,x+37,y+9),fill='#efc8a5')
        draw.pieslice((x-40,y-77,x+40,y-11),180,360,fill=INK)
        draw.ellipse((x-18,y-32,x-13,y-26),fill=INK)
        draw.ellipse((x+13,y-32,x+18,y-26),fill=INK)
        draw.arc((x-11,y-24,x+11,y-6),15,165,fill='#9c6447',width=2)
        draw.rounded_rectangle((x+18,y+45,x+56,y+91),4,fill='#fffdf5')
        for dy in (57,66,75): draw.line((x+26,y+dy,x+47,y+dy),fill=c,width=2)

def background(scene, index):
    if FILM=='matin': return meeting_background(scene,index)
    im = Image.new('RGB',(W,H),PAPER)
    d = ImageDraw.Draw(im)
    d.ellipse((1010,-170,1390,210),fill='#e8eddb')
    d.rounded_rectangle((42,30,80,68),12,fill=GREEN)
    d.line((54,55,61,45,70,42),fill='#dfedac',width=4)
    text(d,(94,35),'LE RAYON EN IMAGES',18,GREEN,True)
    text(d,(W-65,37),f'{index+1:02} / {len(SCENES):02}',18,GREEN,True,align='center')
    text(d,(58,89),scene['chapter'].upper(),17,GREEN,True)
    text(d,(56,119),scene['title'],36,INK,True)
    d.rounded_rectangle((40,190,1240,489),26,fill='#ffffff',outline='#dbe2d1',width=2)
    avatar(d,190,297,scene['from'])
    avatar(d,1090,297,scene['to'])
    text(d,(190,407),scene['from'],21,color(scene['from']),True,align='center')
    text(d,(1090,407),scene['to'],21,color(scene['to']),True,align='center')
    text(d,(190,443),scene['roleFrom'],15,'#65766b',width=276,align='center')
    text(d,(1090,443),scene['roleTo'],15,'#65766b',width=276,align='center')
    d.rounded_rectangle((361,225,919,350),20,fill='#edf2e5')
    d.polygon([(361,270),(340,282),(361,295)],fill='#edf2e5')
    text(d,(640,244),scene['message'],28,INK,True,width=520,align='center',spacing=8)
    d.line((355,388,917,388),fill='#ced9c4',width=4)
    d.polygon([(919,388),(905,381),(905,395)],fill=GREEN)
    text(d,(640,433),'INFORMATIONS  →  MISSION  →  RÉSULTAT',13,'#6b7b67',True,align='center')
    text(d,(640,504),scene['note'],20,GREEN,True,width=1170,align='center')
    d.rounded_rectangle((40,551,1240,658),18,fill='#e9eddf')
    text(d,(58,676),'LES ÉCHANGES ENTRE AGENTS',12,'#6b7b67',True)
    text(d,(988,676),'Explication · Voix de synthèse',12,'#6b7b67')
    return im

TEAM = [('Leader','Coordonne'),('Agent courrier','Lit les sources'),('Agent données','Simule et intègre'),('Agent contrôle','Vérifie avant / après'),('Agent rayon','Dialogue avec le magasin'),('Agent articles','Expert au besoin'),('Agent tendances','Expert au besoin'),('Agent audit-stock','Expert au besoin')]
SEATS={name:(170+(i%4)*313,167 if i<4 else 420) for i,(name,_) in enumerate(TEAM)}
FILES=[('vente','Ventes','Sorties'),('casse','Casse','Sorties'),('don','Dons','Sorties'),('livraison','Livraison','Réception'),('web','Webtélévente','Offres du jour'),('mercalys','Mercalys','Fiches articles')]
SPRITES={}

def meeting_background(scene,index):
    im=Image.new('RGB',(W,H),PAPER)
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((34,23,267,54),12,fill=GREEN)
    text(d,(49,28),'LA RÉUNION DU MATIN',16,'white',True)
    text(d,(1020,30),'EXEMPLE EXPLIQUÉ',14,'#687566',True)
    text(d,(1210,30),f'{index+1:02}/{len(SCENES):02}',14,GREEN,True,align='center')
    text(d,(38,63),scene['title'],30,INK,True)
    for name,role in TEAM:
        x,y=SEATS[name]
        active=name==scene['from']
        target=name==scene['to']
        d.rounded_rectangle((x-144,y-63,x+144,y+86),18,fill='#e4edda' if active else '#ffffff',outline=color(name) if active or target else '#e1e5d8',width=3 if active else 1)
        if name not in SPRITES:
            sprite=Image.new('RGBA',(220,225),(0,0,0,0))
            avatar(ImageDraw.Draw(sprite),110,95,name)
            SPRITES[name]=sprite.resize((94,96),Image.Resampling.LANCZOS)
        im.paste(SPRITES[name],(x-47,y-61),SPRITES[name])
        text(d,(x,y+36),name,21,color(name),True,align='center')
        text(d,(x,y+65),'PREND LA PAROLE' if active else role,12,color(name) if active else '#687566',active,align='center')
    d.rounded_rectangle((42,261,1238,351),25,fill='#dedfcf',outline='#c4cbbb',width=2)
    focus=scene['focus']
    for i,(key,label,kind) in enumerate(FILES):
        x=63+i*194
        selected='all' in focus or key in focus
        red=scene['state']=='erreur' and key=='livraison'
        fill='#f7ddd4' if red else ('#eff5df' if selected else '#f9faf5')
        border='#b24f37' if red else ('#17634b' if selected else '#c9d1c1')
        d.rounded_rectangle((x,276,x+180,336),9,fill=fill,outline=border,width=2)
        text(d,(x+90,281),label,20,border,True,align='center')
        text(d,(x+90,310),'À VÉRIFIER' if red else kind,12,border,align='center')
    text(d,(640,517),scene['note'],17,'#a84734' if scene['state']=='erreur' else GREEN,True,width=1190,align='center')
    d.rounded_rectangle((35,550,1245,698),18,fill='#ffffff',outline=color(scene['from']),width=2)
    text(d,(54,559),scene['from'].upper(),19,color(scene['from']),True)
    target='→ '+scene['to']
    d.text((1222-d.textlength(target,font=font(16)),563),target,font=font(16),fill='#687566')
    if scene['state'] in ('envoi','renvoi'):
        # Le mail part du magasin ; le responsable est le locuteur de cette scène.
        d.rounded_rectangle((1122,61,1206,99),7,fill='#dfedac',outline=GREEN,width=2)
        d.line((1124,64,1164,84,1204,64),fill=GREEN,width=2)
        human=Image.new('RGBA',(220,225),(0,0,0,0))
        avatar(ImageDraw.Draw(human),110,95,'Responsable du rayon')
        human=human.resize((80,84),Image.Resampling.LANCZOS)
        im.paste(human,(53,596),human)
        d.rounded_rectangle((137,612,169,668),5,fill=INK)
        d.rectangle((141,619,165,657),fill='#dfedac')
        d.line((144,635,153,641,162,635),fill=GREEN,width=2)
    return im

def spoken_text(scene):
    # Orthographe de synthèse seulement : l'image et les sous-titres gardent « Leader ».
    return re.sub(r'\bLeader\b','lideur',scene['voice'])

def audio_key(scene):
    return hashlib.sha256(json.dumps([VOICE,RATE,spoken_text(scene),'leader-fr-v1'],ensure_ascii=False).encode()).hexdigest()

def synthesize():
    # Seule la narration documentaire est transmise au service vocal Microsoft.
    # Les fichiers métier, courriels et configurations ne sont jamais envoyés.
    import edge_tts
    async def make():
        for i,scene in enumerate(SCENES):
            signature=WORK/f'{i:02}.neural.sha256'
            wav=WORK/f'{i:02}.wav'
            timing=WORK/f'{i:02}.phrases.json'
            digest=audio_key(scene)
            if signature.exists() and signature.read_text()==digest and wav.exists() and timing.exists():
                continue
            mp3=WORK/f'{i:02}.neural.mp3'
            for attempt in range(3):
                bounds=[]
                try:
                    voice=edge_tts.Communicate(spoken_text(scene),VOICE,rate=RATE,boundary='SentenceBoundary',receive_timeout=40)
                    with mp3.open('wb') as audio:
                        async for chunk in voice.stream():
                            if chunk['type']=='audio': audio.write(chunk['data'])
                            elif chunk['type']=='SentenceBoundary':
                                start=chunk['offset']/10_000_000
                                caption=re.sub(r'\blideur\b','Leader',html.unescape(chunk['text']),flags=re.I)
                                bounds.append([start,start+chunk['duration']/10_000_000,caption])
                    if not bounds or mp3.stat().st_size<1000: raise RuntimeError('Narration vide ou sans repères de phrases.')
                    break
                except Exception:
                    if attempt==2: raise
                    await asyncio.sleep(2*(attempt+1))
            subprocess.run([FFMPEG,'-y','-v','error','-i',str(mp3),'-ac','1','-ar','48000',str(wav)],check=True)
            timing.write_text(json.dumps(bounds,ensure_ascii=False),encoding='utf-8')
            signature.write_text(digest)
            print(f'Voix naturelle : scène {i+1}/{len(SCENES)}',flush=True)
    asyncio.run(make())

def stamp(seconds):
    ms = round(seconds * 1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02}.{ms%1000:03}'

def refresh_player(chapters,total):
    page=DOC/PLAYER
    if not page.exists(): return
    def clock(n): return f'{int(n)//60}:{int(n)%60:02}'
    buttons='\n'.join(f'<button type="button" data-time="{c["start"]}" aria-label="Aller à {clock(c["start"])} : {html.escape(c["title"],quote=True)}"><span>{clock(c["start"])}</span>{html.escape(c["title"])}</button>' for c in chapters)
    transcript='\n'.join(f'<h3>{i+1}. {html.escape(s["title"])}</h3><p>{html.escape(s["voice"])}</p>' for i,s in enumerate(SCENES))
    content=page.read_text(encoding='utf-8')
    version=hashlib.sha256((OUT/MP4_NAME).read_bytes()).hexdigest()[:12]
    media=f'assets/{OUT.name}/{MP4_NAME}'
    content=re.sub(r'src="'+re.escape(media)+r'(?:\?[^\"]*)?"',f'src="{media}?v={version}"',content)
    content=re.sub(r'FILM · [0-9:]+','FILM · '+clock(total),content)
    content=re.sub(r'(<div class="chapters" aria-label="Chapitres du film">).*?</div>',lambda m:m[1]+buttons+'</div>',content,flags=re.S)
    content=re.sub(r'<div class="transcript">.*?</div></details>',lambda m:'<div class="transcript">'+transcript+'</div></details>',content,flags=re.S)
    page.write_text(content,encoding='utf-8')

def main():
    global FILM,MP4_NAME,PLAYER,WORK,OUT,SCENES
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--film',choices=['interactions','matin'],default='interactions')
    parser.add_argument('--scene',type=int,help='Regénérer uniquement cette scène, en réutilisant les autres segments déjà produits.')
    args=parser.parse_args()
    selected=args.scene
    FILM=args.film
    if FILM=='matin':
        SCENES=json.loads((SOURCE/'scenario-matin.json').read_text(encoding='utf-8'))
        WORK=ROOT/'scratch/video-matin'
        OUT=DOC/'assets/video-matin'
        PLAYER='video-matin-agents.html'
        MP4_NAME='matin-agents.mp4'
        WORK.mkdir(parents=True,exist_ok=True)
        OUT.mkdir(parents=True,exist_ok=True)
    if selected is not None and not 1<=selected<=len(SCENES):
        parser.error('--scene doit désigner une scène du film choisi.')
    synthesize()
    print('Narration française prête.',flush=True)
    total=0
    chapters=[]
    cues=['WEBVTT','']
    for i,s in enumerate(SCENES):
        wav=WORK/f'{i:02}.wav'
        with wave.open(str(wav)) as sound:
            duration=sound.getnframes()/sound.getframerate()+.8
        count=math.ceil(duration*FPS)
        duration=count/FPS
        chapters.append({'title':s['title'],'start':round(total,3),'duration':round(duration,3)})
        # Repères de phrases fournis par le moteur vocal, sans estimation au nombre de mots.
        bounds=json.loads((WORK/f'{i:02}.phrases.json').read_text(encoding='utf-8'))
        sentences=[v for a,b,v in bounds]
        for a,b,sentence in bounds:
            if b>duration+.1: raise ValueError('Sous-titre au-delà de la scène.')
            cues += [f'{stamp(total+a)} --> {stamp(total+b)}',sentence,'']
        clip=WORK/f'{i:02}.mp4'
        clip_signature=WORK/f'{i:02}.render.sha256'
        render_key=hashlib.sha256((Path(__file__).read_text(encoding='utf-8')+json.dumps(s,ensure_ascii=False)+audio_key(s)).encode()).hexdigest()
        if selected and selected!=i+1:
            if not clip.exists() or not clip_signature.exists() or clip_signature.read_text()!=render_key:
                raise SystemExit('Autre segment absent ou modifié : relancer sans --scene.')
            total+=duration
            continue
        base=background(s,i)
        cmd=[FFMPEG,'-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r',str(FPS),'-i','pipe:0','-i',str(wav),'-af','apad','-t',str(duration),'-c:v','libx264','-preset','fast','-crf','22','-pix_fmt','yuv420p','-c:a','aac','-b:a','128k','-ar','48000','-movflags','+faststart',str(clip)]
        with (WORK/f'{i:02}.log').open('wb') as log:
            process=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=log)
            for frame in range(count):
                t=frame/FPS
                im=base.copy()
                d=ImageDraw.Draw(im)
                # Le document traverse l'écran, du demandeur au destinataire.
                phase=(t%3)/3
                ease=phase*phase*(3-2*phase)
                if FILM=='matin':
                    sx,sy=SEATS.get(s['from'],(67,420))
                    tx,ty=SEATS.get(s['to'],(1198,167))
                    if sx==tx: tx=640
                    xx=sx+(tx-sx)*ease
                    d.line((sx,258,tx,258),fill='#bcc8b1',width=2)
                    d.rounded_rectangle((xx-9,250,xx+9,266),3,fill=color(s['from']))
                    if s['from'] in SEATS:
                        # Petites ondes près du personnage qui parle.
                        rad=8+4*math.sin(t*7)
                        d.arc((sx+30,sy-40-rad,sx+49+rad,sy-15+rad),285,75,fill=color(s['from']),width=3)
                else:
                    xx=365+540*ease
                    d.rounded_rectangle((xx-16,369,xx+16,407),5,fill=GREEN)
                    for yy in (379,387,395): d.line((xx-9,yy,xx+9,yy),fill='#e7efcf',width=2)
                    r=88+3*math.sin(t*3)
                    d.arc((190-r,297-r-10,190+r,297+r+10),185,350,fill=color(s['from']),width=3)
                sentence=next((v for a,b,v in reversed(bounds) if a<=t),sentences[0])
                human_scene=FILM=='matin' and s['state'] in ('envoi','renvoi')
                caption_width=990 if human_scene else 1130
                caption_x=710 if human_scene else 640
                lines=wrapped(d,sentence,caption_width,font(23))
                if len(lines)>3: raise ValueError(f'Sous-titre trop long: {sentence}')
                text(d,(caption_x,(594 if FILM=='matin' else 566)+(3-len(lines))*12),sentence,23,INK,width=caption_width,align='center',spacing=7)
                # Progression globale, avec repères de chapitres.
                for j in range(len(SCENES)):
                    step=1200/len(SCENES)
                    x=40+j*step
                    d.rounded_rectangle((x,709,x+step-7,713),2,fill=GREEN if j<i else '#d6deca')
                    if j==i: d.rounded_rectangle((x,709,x+max(1,(step-7)*frame/count),713),2,fill=GREEN)
                if frame==min(count-1,FPS*2):
                    im.save(WORK/f'scene-{i+1:02}.png')
                    if i==0: im.save(OUT/'affiche.jpg',quality=94)
                process.stdin.write(im.tobytes())
            process.stdin.close()
            if process.wait()!=0: raise RuntimeError((WORK/f'{i:02}.log').read_text())
        clip_signature.write_text(render_key)
        total+=duration
        print(f'Scène {i+1}/{len(SCENES)} · {duration:.1f} s',flush=True)
    listing=WORK/'assemblage.txt'
    listing.write_text('\n'.join(f"file '{i:02}.mp4'" for i in range(len(SCENES))),encoding='utf-8')
    subprocess.run([FFMPEG,'-y','-v','error','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(WORK/'interactions-agents-final.mp4')],check=True)
    (WORK/'interactions-agents-final.mp4').replace(OUT/MP4_NAME)
    (OUT/'sous-titres.vtt').write_text('\n'.join(cues),encoding='utf-8')
    (OUT/'chapitres.json').write_text(json.dumps({'duration':round(total,3),'chapters':chapters},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    refresh_player(chapters,total)
    sheet=Image.new('RGB',(1280,math.ceil(len(SCENES)/3)*240),PAPER)
    for i in range(len(SCENES)):
        small=Image.open(WORK/f'scene-{i+1:02}.png').resize((426,240))
        sheet.paste(small,((i%3)*426,(i//3)*240))
    sheet.save(WORK/'planche.png')
    print(f'Vidéo terminée : {total:.1f} secondes · {OUT}',flush=True)

if __name__=='__main__': main()
