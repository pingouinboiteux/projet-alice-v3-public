"""Check explicit French volume values; this does not authorize an operation."""
import re
from action_policy import normalize

SMALL=['zero','un','deux','trois','quatre','cinq','six','sept','huit','neuf',
       'dix','onze','douze','treize','quatorze','quinze','seize',
       'dix sept','dix huit','dix neuf']

def french_number(value):
    if value<20:return SMALL[value]
    if value==100:return 'cent'
    if value>=80:
        rest=value-80
        return 'quatre vingts' if not rest else 'quatre vingt '+SMALL[rest]
    if value>=70:
        rest=value-60
        return 'soixante '+('et ' if rest==11 else '')+SMALL[rest]
    tens,unit=divmod(value,10)
    base={2:'vingt',3:'trente',4:'quarante',5:'cinquante',6:'soixante'}[tens]
    return base if not unit else base+(' et ' if unit==1 else ' ')+SMALL[unit]

WORDS={french_number(i):i for i in range(101)}
WORDS['quatre vingt']=80
for base,value in [('septante',70),('huitante',80),('octante',80),('nonante',90)]:
    for unit in range(10):WORDS[base+(' et un' if unit==1 else ' '+SMALL[unit] if unit else '')]=value+unit
NUMBER_WORDS=set(' '.join(WORDS).split())|{'mille','million','millions','milliard','milliards','cents','moins','virgule'}
TOKEN='(?:'+'|'.join(sorted(NUMBER_WORDS,key=len,reverse=True))+')'
WORD_PATTERN=re.compile(r'(?<!\w)'+TOKEN+r'(?:\s+'+TOKEN+r')*(?!\w)')

def explicit_volume_values(text):
    """Longest number phrases, not substrings such as vingt within quatre-vingt."""
    clean=normalize(text)
    # A percent unit does not constitute a request for the value one hundred.
    clean=re.sub(r'\bpour\s+cent\b|\bpourcent(?:s)?\b','%',clean)
    values=set()
    for match in re.finditer(r'(?<![\w.,+\-])\d+(?:[ \u00a0\u202f]+\d+)*(?![\w.,])',clean):
        token=match.group()
        if token.isdecimal() and int(token)<=100:values.add(int(token))
    # Hyphens inside written French numbers are spelling, unlike a minus sign.
    words=re.sub(r'(?<=[a-z])[-\u2010\u2011](?=[a-z])',' ',clean)
    words=re.sub(r'\s+',' ',words)
    for match in WORD_PATTERN.finditer(words):
        if match.group() not in WORDS:continue
        if match.group()=='un':
            # The indefinite article is not the numerical level one.
            before,after=words[:match.start()],words[match.end():]
            if not (words=='un' or re.match(r'\s*%',after) or re.search(r'\ba\s+$',before)):
                continue
        values.add(WORDS[match.group()])
    if re.search(r'\b(?:maximum|max)\b',clean):values.add(100)
    if re.search(r'\bmoitie\b',clean):values.add(50)
    return values

def supports_volume(text,value):
    return type(value) is int and value in explicit_volume_values(text)
