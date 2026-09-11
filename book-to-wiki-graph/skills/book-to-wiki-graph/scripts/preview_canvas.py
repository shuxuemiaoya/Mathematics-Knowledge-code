#!/usr/bin/env python3
"""Render a local Canvas geometry preview (Pillow optional; not an Obsidian screenshot)."""
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


def render(canvas: Path, output: Path, font: Path, width: int = 2400) -> None:
    from PIL import Image, ImageDraw, ImageFont
    data = json.loads(canvas.read_text(encoding="utf-8"))
    nodes = data["nodes"]
    by_id = {node["id"]:node for node in nodes}
    x0,y0 = min(n['x'] for n in nodes)-80,min(n['y'] for n in nodes)-80
    x1,y1 = max(n['x']+n['width'] for n in nodes)+80,max(n['y']+n['height'] for n in nodes)+80
    scale = width / (x1-x0)
    image = Image.new('RGB',(width,math.ceil((y1-y0)*scale)), '#202122')
    draw = ImageDraw.Draw(image)
    colors = {'1':'#c86e75','2':'#c19e59','3':'#aaa45e','4':'#6ca58a','5':'#6ba6b4','6':'#a989bb'}
    def pt(x,y): return ((x-x0)*scale,(y-y0)*scale)
    def face(size): return ImageFont.truetype(str(font), max(9,round(size*scale)))
    def label(node):
        text = node.get('label',node.get('text','')).split('\n')[0].lstrip('# ')
        return re.sub(r'\[([^\]]+)\]\([^)]*\)',r'\1',text)
    for node in nodes:
        if node['type'] != 'group': continue
        a,b=pt(node['x'],node['y']),pt(node['x']+node['width'],node['y']+node['height'])
        draw.rounded_rectangle([a,b],radius=5,fill='#252627',outline='#626469',width=max(1,round(scale)))
        draw.text(pt(node['x']+12,node['y']+12),label(node),font=face(23),fill='#c5c6c8')
    def endpoint(node,side):
        x,y,w,h=node['x'],node['y'],node['width'],node['height']
        return {'right':(x+w,y+h/2),'left':(x,y+h/2),'top':(x+w/2,y),'bottom':(x+w/2,y+h)}[side]
    for edge in data['edges']:
        a,b=by_id[edge['fromNode']],by_id[edge['toNode']]
        p,q=endpoint(a,edge['fromSide']),endpoint(b,edge['toSide'])
        amount=min(160,max(70,math.dist(p,q)*.3))
        vectors={'right':(amount,0),'left':(-amount,0),'top':(0,-amount),'bottom':(0,amount)}
        u,v=vectors[edge['fromSide']],vectors[edge['toSide']]
        c=(p[0]+u[0],p[1]+u[1]);d=(q[0]+v[0],q[1]+v[1])
        points=[]
        for step in range(41):
            t=step/40;s=1-t
            points.append(pt(s**3*p[0]+3*s*s*t*c[0]+3*s*t*t*d[0]+t**3*q[0],s**3*p[1]+3*s*s*t*c[1]+3*s*t*t*d[1]+t**3*q[1]))
        color=colors.get(edge.get('color'),edge.get('color','#999999'))
        draw.line(points,fill=color,width=max(1,round(2*scale)))
        if edge.get('toEnd','arrow')!='none':
            angle=math.atan2(points[-1][1]-points[-2][1],points[-1][0]-points[-2][0]);size=max(4,7*scale)
            draw.polygon([points[-1],(points[-1][0]-size*math.cos(angle-.5),points[-1][1]-size*math.sin(angle-.5)),(points[-1][0]-size*math.cos(angle+.5),points[-1][1]-size*math.sin(angle+.5))],fill=color)
        text=edge.get('label','').replace('主线 · ','')
        if text:
            middle=points[len(points)//2]; f=face(14)
            bb=draw.textbbox(middle,text,font=f);draw.rectangle(bb,fill='#252627');draw.text(middle,text,font=f,fill='#c5c6c8')
    for node in nodes:
        if node['type']=='group':continue
        a,b=pt(node['x'],node['y']),pt(node['x']+node['width'],node['y']+node['height'])
        color=colors.get(node.get('color'),'#686a6d')
        draw.rounded_rectangle([a,b],radius=max(2,round(6*scale)),fill='#292725' if node.get('color')=='2' else '#242628',outline=color,width=max(1,round(2*scale)))
        text=label(node); f=face(17)
        while draw.textlength(text,font=f)>(node['width']-20)*scale and len(text)>3:text=text[:-2]+'…'
        draw.text(pt(node['x']+10,node['y']+(node['height']-22)/2),text,font=f,fill='#c5b4ec')
    output.parent.mkdir(parents=True,exist_ok=True)
    image.save(output)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('canvas',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--font',type=Path,required=True);parser.add_argument('--width',type=int,default=2400)
    args=parser.parse_args();render(args.canvas,args.output,args.font,args.width)
