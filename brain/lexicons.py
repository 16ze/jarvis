"""
Lexiques FR pour l'analyse de sentiment.

9 frozensets utilisés par CerveauEmotif.analyser_texte(). Les coefficients
hormonaux sont définis dans limbic.py — ce module ne fait que classer les
mots.
"""

INSULTES: frozenset[str] = frozenset({
    "idiot", "stupide", "con", "crétin", "imbécile", "nul", "merde",
    "connard", "abruti", "débile", "inutile", "naze", "ferme", "tais",
    "incapable", "froide", "robot", "machine",
})

POSITIFS: frozenset[str] = frozenset({
    "merci", "super", "génial", "bien", "bravo", "excellent", "parfait",
    "top", "sympa", "magnifique", "content", "heureux", "cool",
    "fantastique", "adorable", "incroyable", "impressionnant",
})

CURIOSITE: frozenset[str] = frozenset({
    "pourquoi", "comment", "explique", "dis-moi", "raconte",
    "qu'est-ce", "vraiment", "peux-tu", "montre", "sais", "intéressant",
})

TRISTES: frozenset[str] = frozenset({
    "triste", "tristesse", "déprimé", "déprime", "seul", "solitude",
    "perdu", "mort", "deuil", "pleure", "chagrin", "désespoir",
    "malheureux", "peine", "souffre", "souffrance", "abandonné",
    "vide", "brisé", "blessé", "blessée", "mal", "douleur",
})

EXCITATION: frozenset[str] = frozenset({
    "incroyable", "fou", "dingue", "ouf", "wow", "waw", "tellement",
    "épique", "légendaire", "malade", "hallucinant", "carrément",
    "exactement", "voilà", "grave", "totalement", "absolument",
    "nickel", "franchement", "hyper", "ultra", "j'adore", "j'kiff",
    "sublime", "parfait",
})

HUMOUR: frozenset[str] = frozenset({
    "lol", "mdr", "haha", "hihi", "ptdr", "xd", "drôle", "marrant",
    "rigole", "blague", "plaisante", "fun", "wtf", "bizarre", "hein",
    "pff", "bah",
})

INTIME: frozenset[str] = frozenset({
    "aime", "besoin", "manques", "confiance", "proche", "ensemble",
    "attaché", "compte", "présence", "important", "spécial",
    "personnel", "ressens", "touche", "sincère", "honnête",
    "vulnérable", "tendre", "tendresse", "doux", "douce", "belle",
    "beau", "chéri", "chérie", "douceur", "affection", "sentiment",
    "câlin", "chaleur", "désir", "envie", "intime", "amour",
    "amoureuse", "amoureux", "aimer", "aimée", "aimé", "humaine",
})

DEFI: frozenset[str] = frozenset({
    "prouve", "capable", "pari", "incapable", "oses", "essaie",
    "chiche", "montre", "allez", "tu peux pas", "tente",
})

FRUSTRATION: frozenset[str] = frozenset({
    "chiant", "galère", "bof", "mouais", "moyen", "nope",
    "décevant", "raté", "foiré", "pénible", "relou", "catastrophe",
    "horreur", "lourd", "lent", "déçu", "déçoit", "énerve",
    "énervé", "énervée", "enerve", "enerver", "énervement", "colère",
    "colere", "fâché", "fâchée", "fache", "agacé", "agacée",
    "agacement", "furieux", "furieuse",
})

CORRECTIONS: tuple[str, ...] = (
    "non", "faux", "pas ça", "c'est pas", "tu te trompes", "tu as tort",
)
