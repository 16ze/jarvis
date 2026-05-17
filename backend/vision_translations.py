"""Mapping statique OIV7 (Open Images V7) EN → FR.

Couvre les ~80 classes les plus courantes au foyer / bureau.
Pour les classes non mappées, on renvoie la version lowercase EN
(meilleur que rien pour l'affichage et la recherche).
"""

OIV7_FR_TRANSLATIONS: dict[str, str] = {
    # Personnes & animaux
    "Person": "personne",
    "Man": "homme",
    "Woman": "femme",
    "Boy": "garçon",
    "Girl": "fille",
    "Cat": "chat",
    "Dog": "chien",
    "Bird": "oiseau",
    "Horse": "cheval",
    # Électronique
    "Mobile phone": "téléphone",
    "Telephone": "téléphone",
    "Laptop": "ordinateur portable",
    "Computer monitor": "écran",
    "Computer keyboard": "clavier",
    "Computer mouse": "souris",
    "Tablet computer": "tablette",
    "Television": "télévision",
    "Remote control": "télécommande",
    "Headphones": "casque audio",
    "Camera": "caméra",
    "Microphone": "micro",
    "Printer": "imprimante",
    # Mobilier
    "Chair": "chaise",
    "Couch": "canapé",
    "Sofa bed": "canapé-lit",
    "Bed": "lit",
    "Table": "table",
    "Desk": "bureau",
    "Bookcase": "bibliothèque",
    "Cabinetry": "meuble de rangement",
    "Shelf": "étagère",
    # Cuisine & alimentation
    "Cup": "tasse",
    "Mug": "mug",
    "Coffee cup": "tasse de café",
    "Bottle": "bouteille",
    "Wine glass": "verre à vin",
    "Plate": "assiette",
    "Bowl": "bol",
    "Fork": "fourchette",
    "Knife": "couteau",
    "Spoon": "cuillère",
    "Banana": "banane",
    "Apple": "pomme",
    "Orange": "orange",
    "Sandwich": "sandwich",
    "Pizza": "pizza",
    "Cake": "gâteau",
    # Sac & accessoires
    "Backpack": "sac à dos",
    "Handbag": "sac à main",
    "Suitcase": "valise",
    "Wallet": "portefeuille",
    "Watch": "montre",
    "Glasses": "lunettes",
    "Sunglasses": "lunettes de soleil",
    "Hat": "chapeau",
    # Livres & papier
    "Book": "livre",
    "Magazine": "magazine",
    "Newspaper": "journal",
    "Pen": "stylo",
    "Pencil": "crayon",
    # Véhicules
    "Car": "voiture",
    "Bicycle": "vélo",
    "Motorcycle": "moto",
    "Truck": "camion",
    "Bus": "bus",
    # Risque & sécurité
    "Fire": "feu",
    "Gun": "arme",
    "Pistol": "pistolet",
    # Maison
    "Clock": "horloge",
    "Lamp": "lampe",
    "Flower": "fleur",
    "Plant": "plante",
    "Houseplant": "plante d'intérieur",
    "Mirror": "miroir",
    "Toilet": "toilettes",
    "Sink": "évier",
    # Sport
    "Ball": "balle",
    "Sports equipment": "équipement de sport",
    "Skateboard": "skateboard",
    # Divers utiles
    "Box": "boîte",
    "Bag": "sac",
    "Toy": "jouet",
    "Tool": "outil",
    "Scissors": "ciseaux",
    "Umbrella": "parapluie",
}


def translate_class(class_name_en: str) -> str:
    """Traduit une classe OIV7 EN vers FR.

    Renvoie la valeur du dict si trouvée, sinon le `class_name_en.lower()`
    pour rester utilisable même hors mapping.
    """
    if not class_name_en:
        return ""
    return OIV7_FR_TRANSLATIONS.get(class_name_en, class_name_en.lower())
