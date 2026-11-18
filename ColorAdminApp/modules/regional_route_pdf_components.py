"""Componentes vetoriais do roteiro, com os icones e raios do template original."""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Flowable, Paragraph

ICONS={'users':'f0c0','calendar':'f073','pin':'f3c5','clock':'f017','map':'f279','tag':'f02b','sun':'f185','route':'f4d7','shield':'f3ed','coffee':'f0f4'}


def icon(name,color=None):
    if 'RouteIcons' not in pdfmetrics.getRegisteredFontNames():
        # Static is served separately and excluded from the Vercel Python bundle.
        font_path = Path(__file__).resolve().parent.parent / 'assets/fonts/fa-solid-900.ttf'
        pdfmetrics.registerFont(TTFont('RouteIcons',str(font_path)))
    tint=f' color="{color}"' if color else ''
    return f'<font name="RouteIcons"{tint}>{chr(int(ICONS[name],16))}</font>'


class RoundedBadge(Flowable):
    def __init__(self,text,width,fill='#eef2f5',color='#243746',border='#c8d1da',symbol=None,size=6.8,bold=True,padding=4,radius=2.5,center=False,symbol_color=None):
        super().__init__()
        self.width=width;self.fill=colors.HexColor(fill);self.border=colors.HexColor(border) if border else None
        self.padding=padding;self.radius=radius
        content=(icon(symbol,symbol_color)+' &nbsp; ' if symbol else '')+text
        self.paragraph=Paragraph(content,ParagraphStyle('route-badge',fontName='Helvetica-Bold' if bold else 'Helvetica',fontSize=size,leading=size+1.5,textColor=colors.HexColor(color),alignment=1 if center else 0))

    def wrap(self,available_width,available_height):
        self.width=min(self.width,available_width)
        _,height=self.paragraph.wrap(max(1,self.width-2*self.padding),available_height)
        self.height=height+2*self.padding
        return self.width,self.height

    def draw(self):
        canvas=self.canv;canvas.saveState();canvas.setFillColor(self.fill)
        if self.border:canvas.setStrokeColor(self.border);canvas.setLineWidth(.5)
        canvas.roundRect(0,0,self.width,self.height,self.radius,fill=1,stroke=bool(self.border))
        self.paragraph.drawOn(canvas,self.padding,self.padding)
        canvas.restoreState()


class RoundedVisitCard(Flowable):
    def __init__(self,table,width,background='#fdfdfd',qr_width=78):
        super().__init__();self.table=table;self.width=width;self.background=background;self.qr_width=qr_width

    def wrap(self,available_width,available_height):
        self.width=min(self.width,available_width)
        _,self.height=self.table.wrap(self.width,available_height)
        return self.width,self.height

    def draw(self):
        canvas=self.canv;canvas.saveState()
        canvas.setFillColor(colors.HexColor(self.background));canvas.setStrokeColor(colors.HexColor('#e2e7eb'));canvas.setLineWidth(.6)
        canvas.roundRect(0,0,self.width,self.height,3.75,fill=1,stroke=1)
        canvas.setStrokeColor(colors.HexColor('#348fe2'));canvas.setLineWidth(3);canvas.setLineCap(1)
        canvas.line(1.5,3.5,1.5,self.height-3.5)
        canvas.setLineWidth(.5);canvas.setStrokeColor(colors.HexColor('#cccccc'));canvas.setDash(2,2)
        canvas.line(self.width-self.qr_width,7,self.width-self.qr_width,self.height-7)
        canvas.restoreState();self.table.drawOn(canvas,0,0)
