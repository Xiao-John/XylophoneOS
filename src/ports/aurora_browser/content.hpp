// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <QtCore/QFile>
#include <QtCore/QDir>
#include <QtCore/QByteArray>
#include <QtCore/QStringList>
namespace browser {
// The provider accepts read-only /web files. No URL grants a file write, spawn,
// device or kernel privilege. HTTP is a separate future provider.
inline QString resolve(QString value, const QString &base) {
    if(value.size()>256 || value.contains(QChar('\0')) || value.contains('\\') || value.contains('%')) return {};
    if(value.startsWith("file:")) value=value.mid(5);
    if(value.contains(':') || value.contains('?')) return {};
    value=value.section('#',0,0);
    if(value.isEmpty()) value=base;
    if(!value.startsWith('/')) value=base.section('/',0,-2)+"/"+value;
    value=QDir::cleanPath(value);
    if(!value.startsWith("/web/"))return {};
    return value;
}
inline bool read(const QString &path,QByteArray &bytes,int limit,QString &error) {
    QFile file(path);
    if(!file.open(QIODevice::ReadOnly)){error="Page or resource missing";return false;}
    // Size is checked before allocation; read at most limit+1 handles changes.
    if(file.size()<0 || file.size()>limit){error="Resource byte budget exceeded";return false;}
    bytes=file.read(limit+1);
    if(file.error()!=QFileDevice::NoError || bytes.size()>limit){error="Resource read failed or grew";return false;}
    return true;
}
inline bool decimal(QString text,double maximum,bool fraction=true) {
    if(text.isEmpty()||text.size()>8)return false;
    int dots=0;for(auto c:text){if(c=='.'&&fraction){if(++dots>1)return false;}else if(c<'0'||c>'9')return false;}
    bool ok=false;double value=text.toDouble(&ok);return ok&&value>=0&&value<=maximum;
}
inline bool length(QString text,int maximum,bool percent=false) {
    if(text=="0")return true;
    if(text.endsWith("px"))return decimal(text.chopped(2),maximum);
    if(percent&&text.endsWith('%'))return decimal(text.chopped(1),100);
    return false;
}
inline bool css_color(QString text) {
    if(QStringList{"white","black","transparent","navy","teal","blue","purple","red"}.contains(text))return true;
    if(!text.startsWith('#')||(text.size()!=4&&text.size()!=7))return false;
    for(auto c:text.mid(1)){if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;}return true;
}
inline bool css_value(QString key,QString value) {
    auto words=value.simplified().split(' ');
    if(QStringList{"color","background","background-color","border-color"}.contains(key))return css_color(value);
    if(key=="font-family")return value=="dejavu sans"||value=="sans-serif";
    if(key=="font-style")return value=="normal"||value=="italic";
    if(key=="font-weight")return QStringList{"normal","bold","100","200","300","400","500","600","700","800","900"}.contains(value);
    if(key=="font-size")return length(value,96);
    if(key=="line-height")return value=="normal"||decimal(value,4)||length(value,128);
    if(key=="letter-spacing")return value=="normal"||length(value,8);
    if(key=="margin"||key=="padding"||key.startsWith("margin-")||key.startsWith("padding-")) {
        if(!QStringList{"margin","margin-top","margin-bottom","margin-left","margin-right","padding","padding-top","padding-bottom","padding-left","padding-right"}.contains(key)||words.size()>4)return false;
        for(const auto &w:words)if(!length(w,256)&&!(w=="auto"&&key.startsWith("margin")))return false;return true;
    }
    if(QStringList{"width","height","max-width","max-height","min-width","min-height"}.contains(key))return value=="auto"||length(value,4096,true);
    if(QStringList{"border","border-top","border-bottom","border-left","border-right"}.contains(key))return words.size()==3&&length(words[0],16)&&words[1]=="solid"&&css_color(words[2]);
    if(key=="display")return QStringList{"block","inline","inline-block","flex","none","list-item"}.contains(value);
    if(key=="flex-direction")return value=="row"||value=="column";
    if(key=="align-items")return QStringList{"stretch","center","flex-start","flex-end"}.contains(value);
    if(key=="justify-content")return QStringList{"center","flex-start","flex-end","space-between","space-around"}.contains(value);
    if(key=="text-decoration")return QStringList{"none","underline","line-through"}.contains(value);
    if(key=="text-align")return QStringList{"left","right","center","justify"}.contains(value);
    if(key=="white-space")return QStringList{"normal","pre","pre-wrap"}.contains(value);
    return false;
}
inline bool css_allowed(const QByteArray &input) {
    if(input.size()>8192||input.contains('\0'))return false;
    const QString s=QString::fromLatin1(input).toLower();
    if(s.contains('@')||s.contains('\\')||s.contains("/*")||s.contains("*/"))return false;
    int offset=0,rules=0,declarations=0;
    while(offset<s.size()) {
        if(s.mid(offset).trimmed().isEmpty())break;
        int open=s.indexOf('{',offset),close=s.indexOf('}',open+1);
        if(open<0||close<0||++rules>64||s.indexOf('{',open+1)<close&&s.indexOf('{',open+1)>=0)return false;
        auto selector=s.mid(offset,open-offset).trimmed();if(selector.isEmpty()||selector.size()>128)return false;
        for(auto c:selector)if(!((c>='a'&&c<='z')||(c>='0'&&c<='9')||c=='.'||c=='#'||c=='-'||c=='_'||c==','||c==' '))return false;
        for(const auto &part:s.mid(open+1,close-open-1).split(';')) {
            if(part.trimmed().isEmpty())continue;int colon=part.indexOf(':');if(colon<1||++declarations>256)return false;
            if(!css_value(part.left(colon).trimmed(),part.mid(colon+1).trimmed()))return false;
        }
        offset=close+1;
    }
    return true;
}
inline bool attributes_allowed(QByteArray token,int offset,bool closing) {
    auto ws=[](char c){return c==' '||c=='\t'||c=='\r'||c=='\n'||c=='\f';};int count=0;
    while(offset<token.size()) {
        while(offset<token.size()&&ws(token[offset]))++offset;
        if(offset==token.size())break;
        if(token[offset]=='/'&&offset+1==token.size())break;
        if(closing||++count>16)return false;
        int start=offset;while(offset<token.size()&&((token[offset]>='a'&&token[offset]<='z')||token[offset]=='-'))++offset;
        auto name=token.mid(start,offset-start);while(offset<token.size()&&ws(token[offset]))++offset;
        if(offset==token.size()||token[offset++]!='=')return false;
        while(offset<token.size()&&ws(token[offset]))++offset;
        if(offset==token.size())return false;
        char quote=token[offset]=='\''||token[offset]=='\"'?token[offset++]:0;start=offset;
        while(offset<token.size()&&(quote?token[offset]!=quote:!ws(token[offset])))++offset;
        auto value=token.mid(start,offset-start);if(quote){if(offset==token.size())return false;++offset;}
        if(value.size()>256)return false;
        if(name=="width"||name=="height"){if(!decimal(QString::fromLatin1(value),512,false))return false;}
        else if(!QList<QByteArray>{"href","src","class","id","rel","title","lang","alt"}.contains(name))return false;
    }
    return true;
}
inline bool html_allowed(const QByteArray &input,QString &error) {
    if(input.isEmpty() || input.size()>32768 || input.contains('\0')){error="HTML byte budget or NUL rejected";return false;}
    // Strict bounded lexical admission, then Gumbo performs actual HTML parsing.
    // Requiring balanced supported markup limits malformed/deep trees before
    // recursive layout. This is a prototype subset, not a sanitizer for the Web.
    QStringList stack;int tags=0;int i=0;
    const auto lower=input.toLower();
    while(i<input.size()) {
        if(input[i]!='<'){++i;continue;}
        if(input.mid(i,4)=="<!--") {int end=input.indexOf("-->",i+4);if(end<0){error="Unclosed comment";return false;}i=end+3;continue;}
        bool quote=false;char q=0;int end=i+1;
        for(;end<input.size();++end){char c=input[end];if(quote){if(c==q)quote=false;}else if(c=='\''||c=='\"'){quote=true;q=c;}else if(c=='>')break;}
        if(end>=input.size() || ++tags>256){error="Malformed tag or tag budget";return false;}
        auto token=lower.mid(i+1,end-i-1).trimmed();bool closing=token.startsWith('/');if(closing)token.remove(0,1);
        int nameEnd=0;while(nameEnd<token.size()&&token[nameEnd]!=' '&&token[nameEnd]!='\t'&&token[nameEnd]!='\r'&&token[nameEnd]!='\n'&&token[nameEnd]!='\f'&&token[nameEnd]!='/')++nameEnd;
        auto name=QString::fromLatin1(token.left(nameEnd));
        if(name.startsWith('!')){i=end+1;continue;}
        const QStringList allowed={"html","head","title","body","style","link","h1","h2","h3","p","a","div","span","b","strong","i","em","ul","ol","li","img","br","hr","pre","code"};
        if(!allowed.contains(name)){error="Unsupported HTML tag: "+name;return false;}
        if(!attributes_allowed(token,nameEnd,closing)){error="Unsupported or excessive HTML attributes";return false;}
        const bool leaf=name=="img"||name=="link"||name=="br"||name=="hr";
        if(closing){if(stack.isEmpty()||stack.takeLast()!=name){error="Unbalanced markup rejected";return false;}}
        else if(!leaf){stack.append(name);if(stack.size()>16){error="HTML nesting budget exceeded";return false;}}
        if(name=="style"&&!closing){int stop=lower.indexOf("</style",end+1);if(stop<0 || !css_allowed(input.mid(end+1,stop-end-1))){error="Stylesheet rejected";return false;}i=stop;continue;}
        // Inline style attributes are omitted from this first admitted subset.
        if(token.contains("style=")||token.contains("style =")){error="Use bounded linked or style-block CSS";return false;}
        i=end+1;
    }
    if(!stack.isEmpty()){error="Unclosed markup rejected";return false;}
    return true;
}
}
