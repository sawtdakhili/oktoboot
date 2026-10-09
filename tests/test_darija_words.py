"""
Everyday-Darija benchmark — how often the engine's FIRST suggestion is right.

Not a pass/fail test of every word: it reports top-1 / top-3 hit rates and
lists the misses, and fails only if top-1 drops below MIN_TOP1 (raise that
floor as the engine improves, so it never quietly gets worse).

Always run with learned_db=None — the user's own learned choices outrank the
engine and would hide or fake engine changes (see DECISIONS.md).

Each entry: arabizi -> accepted spellings ("|"-separated). Keep spellings
to what Moroccans actually write; alternatives are listed when both are
common. Edit freely — this list is the definition of "right".
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from oktoboot import engine

MIN_TOP1 = 0.85  # 2026-10-08: 88% after the ranking rewrite; raise as it improves

WORDS = """
salam       سلام
labas       لاباس
wach        واش
kifach      كيفاش
bzaf        بزاف|بزّاف
bezzaf      بزاف|بزّاف
mzyan       مزيان
mezyan      مزيان
mzyana      مزيانة
zwin        زوين
zwina       زوينة
dyal        ديال
dyali       ديالي
dyalek      ديالك
khasni      خاصني
khassek     خاصك
chhal       شحال
wakha       واخا
daba        دابا
gadi        غادي
ghadi       غادي
bghit       بغيت
bghiti      بغيتي
kanbghi     كنبغي
kanbghik    كنبغيك
kayn        كاين
makaynch    ماكاينش
mohammed    محمد|محمّد
sme7li      سمحلي
sbah        صباح
nhar        نهار
lyoum       اليوم|ليوم
ghedda      غدا|غدّا
lbare7      البارح|لبارح
drari       دراري
bnat        بنات
khoya       خويا
khti        ختي
mama        ماما
baba        بابا
dar         دار
flous       فلوس
khdma       خدمة
khdem       خدم
kaykhdem    كيخدم
kaykhdmo    كيخدمو
mchit       مشيت
mcha        مشى|مشا
jit         جيت
klit        كليت
chrebt      شربت
nmchi       نمشي
nmchiw      نمشيو
safi        صافي
la          لا
3afak       عافاك
chokran     شكراً
bslama      بسلامة
smiti       سميتي
smitek      سميتك
fin         فين
fayn        فاين|فين
3lach       علاش
lach        لاش
chkoun      شكون
chno        شنو
achno       اشنو|أشنو
imta        امتى|إمتى|إمتا
ana         انا|أنا
nta         نتا
nti         نتي
howa        هو|هوا
hiya        هي|هيا
homa        هوما
ntoma       نتوما
m3a         مع
3la         على
men         من
had         هاد
hadi        هادي
hadak       هاداك
hadchi      هادشي
walo        والو
bla         بلا
sa3a        ساعة
dima        ديما
mazal       مازال
ba9i        باقي
kolchi      كلشي
chi         شي
bach        باش
fach        فاش
melli       ملي|مللي
walakin     ولكن
hit         حيت
3iyit       عييت
nkhrej      نخرج
sir         سير
aji         أجي|اجي
7mar        حمار
kelb        كلب
9ahwa       قهوة
atay        أتاي|اتاي
khobz       خبز
3ndi        عندي
3ndek       عندك
ma3ndich    ماعنديش
fhemti      فهمتي
fhemt       فهمت
kanfhem     كنفهم
darija      دارجة
sghir       صغير
kbir        كبير
jdid        جديد
bared       بارد
skhoun      سخون
mrid        مريض
tbib        طبيب
sbitar      سبيطار
madrasa     مدرسة
lmadrasa    المدرسة|لمدرسة
mostachfa   مستشفى
7anout      حانوت
souk        سوق
mdina       مدينة
bled        بلاد
lmaghrib    المغرب|لمغرب
lkhobz      الخبز|لخبز
ldar        الدار|لدار
lflous      الفلوس|لفلوس
inchallah   إنشالله|انشالله|إن شاء الله
l7amdollah  الحمدلله|الحمد لله
aakhir      آخر
omar        عمر
"""


def load() -> list[tuple[str, set[str]]]:
    out = []
    for line in WORDS.strip().splitlines():
        latin, accepted = line.split(maxsplit=1)
        out.append((latin, set(accepted.split("|"))))
    return out


def main() -> None:
    words = load()
    top1 = top3 = 0
    misses = []
    for latin, accepted in words:
        got = engine.suggest(latin, learned_db=None)
        if got and got[0] in accepted:
            top1 += 1
        if any(g in accepted for g in got[:3]):
            top3 += 1
        if not got or got[0] not in accepted:
            rank = next((i + 1 for i, g in enumerate(got) if g in accepted), None)
            misses.append((latin, "|".join(sorted(accepted)), got[:3], rank))

    n = len(words)
    print(f"Darija benchmark: {n} words")
    print(f"  top-1: {top1}/{n} ({top1 / n:.0%})")
    print(f"  top-3: {top3}/{n} ({top3 / n:.0%})")
    print("\nMisses (word, expected, top 3, rank of expected or None):")
    for latin, exp, got, rank in misses:
        print(f"  {latin:11} {exp:14} {' '.join(got)}   rank={rank}")

    if top1 / n < MIN_TOP1:
        print(f"\nFAIL: top-1 {top1 / n:.0%} is below the floor {MIN_TOP1:.0%}")
        sys.exit(1)


if __name__ == "__main__":
    main()
