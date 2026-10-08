"""Single pattern-based PII boundary; not detection of arbitrary personal data."""
import re
WORD_RUN = re.compile(r'\b(?:(?:zero|one|two|three|four|five|six|seven|eight|nine|oh)[ ,.-]*){7,}\b', re.I)
DIGITS = re.compile(r'(?<!\w)\+?\d(?:[ ()-]*\d){6,18}(?!\w)')
EMAIL = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I)

def mask_pii(text):
    counts = {'CARD':0, 'PHONE':0, 'EMAIL':0}
    def replace(kind):
        counts[kind] += 1
        return '[' + kind + ']'
    text = EMAIL.sub(lambda _: replace('EMAIL'), str(text))
    def spoken(m):
        words = re.findall(r'[a-z]+', m.group().lower())
        return replace('CARD' if len(words) >= 13 else 'PHONE') + ' '
    text = WORD_RUN.sub(spoken, text)
    text = DIGITS.sub(lambda m: replace('CARD' if len(re.sub(r'\D','',m.group())) >= 13 else 'PHONE'), text)
    return text, counts
