import re
V='aeiou'
def forms(w):
    F={w}
    F|={w+'s',w+'es',w+'ed',w+'d',w+'ing',w+'er',w+'est',w+'r',w+'st',w+'ly'}
    if w.endswith('y') and len(w)>2 and w[-2] not in V: F|={w[:-1]+'ies',w[:-1]+'ied',w[:-1]+'ier',w[:-1]+'iest'}
    if w.endswith('e'): F|={w[:-1]+'ing'}
    if len(w)>2 and w[-1] not in V+'wxy' and w[-2] in V and w[-3] not in V: F|={w+w[-1]+'ing',w+w[-1]+'ed',w+w[-1]+'er',w+w[-1]+'est'}
    if w.endswith('f'): F|={w[:-1]+'ves'}
    if w.endswith('fe'): F|={w[:-2]+'ves'}
    return F
