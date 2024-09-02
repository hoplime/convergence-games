from pathlib import Path

# GENRE_GRADIENT_FORMAT = "bg-gradient-to-t from-{0}/30 to-{0}/30"
GENRE_GRADIENT_FORMAT = "border-{0}"

GENRE_COLORS = {
    "Adventure": "red-500",
    "Comedy": "yellow-500",
    "Corporate Backstabbing": "cyan-800",
    "Cyberpunk": "pink-500",
    "Dark": "black",
    "Detective Story": "teal-500",
    "Drama": "fuchsia-600",
    "Dungeon Crawl": "red-800",
    "Exploration ": "green-500",
    "Fantasy": "orange-500",
    "Heist": "slate-800",
    "Heroic": "amber-500",
    "Historic": "teal-500",
    "Horror": "black",
    "Jungle arena PvP": "lime-700",
    "Mystery": "purple-900",
    "Post-Apocalyptic": "orange-900",
    "Puzzle Dungeon": "indigo-700",
    "Sci-Fi": "purple-500",
    "Serious": "black",
    "Slasher": "red-500",
    "Slice of Life": "yellow-500",
    "Steampunk": "amber-900",
    "Tactics": "slate-500",
    "Worldbuilding": "cyan-500",
    "Zombie": "green-900",
}

GENRE_GRADIENTS = {genre: GENRE_GRADIENT_FORMAT.format(color) for genre, color in GENRE_COLORS.items()}

# We need to write the formatted gradient colors to a file so Tailwind can use them
all_gradient_strings = sorted({GENRE_GRADIENT_FORMAT.format(color) for _, color in GENRE_COLORS.items()})
with open(Path(__file__).parent / "genre_gradients.txt", "w") as f:
    for gradient in all_gradient_strings:
        print(gradient, file=f)
