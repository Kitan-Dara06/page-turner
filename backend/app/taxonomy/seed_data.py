"""
PAGETURNER TAXONOMY SEED
Implements SRS Section 5.5 - Universal Root Hub Architecture.
This list is topologically sorted (parents declared before children) for the DAG migration.

v2.0: Romance genre registers, trope nodes, and subgenre nodes added (28 new nodes).
      TAXONOMY_VERSION bumped to 2.
"""

ROOT_HUBS = [
    "Setting & Environment",
    "Plot Catalysts & Structures",
    "Character Archetypes & Dynamics",
    "Thematic Core",
    "Conflict Typology",
]

# Each node defines its canonical name and a list of parent canonical names.
TROPE_NODES = [
    # --- LEVEL 2: Direct children of Root Hubs ---
    # Setting & Environment Branches
    {"name": "Timeline", "parents": ["Setting & Environment"]},
    {"name": "Scale", "parents": ["Setting & Environment"]},
    {"name": "Reality", "parents": ["Setting & Environment"]},
    # Conflict Typology Branches
    {"name": "Internal Conflict", "parents": ["Conflict Typology"]},
    {"name": "Interpersonal Conflict", "parents": ["Conflict Typology"]},
    {"name": "Systemic/Societal Conflict", "parents": ["Conflict Typology"]},
    {"name": "Survival/External", "parents": ["Conflict Typology"]},
    {"name": "Cosmic/Lovecraftian", "parents": ["Conflict Typology"]},
    # Plot Catalysts Branches
    {"name": "Quests", "parents": ["Plot Catalysts & Structures"]},
    {"name": "Mysteries", "parents": ["Plot Catalysts & Structures"]},
    {
        "name": "Survival",
        "parents": ["Plot Catalysts & Structures", "Survival/External"],
    },
    {"name": "Found Family Formation", "parents": ["Plot Catalysts & Structures"]},
    # Character Archetypes Branches
    {"name": "The Mentor", "parents": ["Character Archetypes & Dynamics"]},
    {"name": "Unreliable Narrator", "parents": ["Character Archetypes & Dynamics"]},
    {"name": "Anti-Hero", "parents": ["Character Archetypes & Dynamics"]},
    {"name": "Relationship Dynamics", "parents": ["Character Archetypes & Dynamics"]},
    # Thematic Core Branches
    {"name": "Existentialism", "parents": ["Thematic Core"]},
    {"name": "Corruption of Power", "parents": ["Thematic Core"]},
    {"name": "Grief/Loss", "parents": ["Thematic Core"]},
    {"name": "Class Struggle", "parents": ["Thematic Core"]},
    {"name": "Man vs Technology", "parents": ["Thematic Core"]},
    {"name": "Obsession", "parents": ["Thematic Core"]},
    {"name": "Identity/Self-Discovery", "parents": ["Thematic Core"]},
    {"name": "Colonialism/Post-Colonialism", "parents": ["Thematic Core"]},
    {"name": "War & Its Aftermath", "parents": ["Thematic Core"]},
    {"name": "Memory & Time", "parents": ["Thematic Core"]},
    {"name": "Redemption Arc", "parents": ["Thematic Core"]},
    # --- LEVEL 3: Direct children of Level 2 nodes ---
    # Settings
    {"name": "Historical", "parents": ["Timeline"]},
    {"name": "Future", "parents": ["Timeline"]},
    {"name": "Alternate History", "parents": ["Timeline"]},
    {"name": "Claustrophobic", "parents": ["Scale"]},
    {"name": "Epic", "parents": ["Scale"]},
    {"name": "Grounded", "parents": ["Reality"]},
    {"name": "Magical Realism", "parents": ["Reality"]},
    {"name": "Hard Sci-Fi", "parents": ["Reality"]},
    {"name": "Space Opera", "parents": ["Reality", "Epic", "Future"]},
    {
        "name": "Military Sci-Fi",
        "parents": ["Reality", "Future", "War & Its Aftermath"],
    },
    {"name": "Omegaverse", "parents": ["Reality"]},
    {"name": "Portal Fantasy", "parents": ["Reality", "Quests"]},
    {"name": "LitRPG", "parents": ["Reality"]},
    {"name": "Dystopia", "parents": ["Future", "Systemic/Societal Conflict"]},
    {
        "name": "Isolated Institution",
        "parents": ["Claustrophobic", "Setting & Environment"],
    },
    {"name": "Magic School", "parents": ["Isolated Institution", "Reality"]},
    {"name": "Cyberpunk", "parents": ["Future", "Man vs Technology"]},
    {
        "name": "Dark Academia",
        "parents": ["Isolated Institution", "Obsession", "Class Struggle"],
    },
    # ── Relationship Dynamics base (must come before trope children) ────
    {
        "name": "Enemies to Lovers",
        "parents": ["Relationship Dynamics", "Interpersonal Conflict"],
    },
    {"name": "Grumpy/Sunshine", "parents": ["Relationship Dynamics"]},
    {"name": "Reverse Harem", "parents": ["Relationship Dynamics"]},
    {"name": "Why Choose", "parents": ["Relationship Dynamics"]},
    {"name": "Forced Proximity", "parents": ["Relationship Dynamics"]},
    {"name": "One Bed", "parents": ["Forced Proximity"]},
    {
        "name": "Forbidden Romance",
        "parents": ["Relationship Dynamics", "Systemic/Societal Conflict"],
    },
    {"name": "Stepbrother Romance", "parents": ["Forbidden Romance"]},
    {"name": "Dubcon", "parents": ["Relationship Dynamics", "Obsession"]},
    {
        "name": "Captive Romance",
        "parents": ["Relationship Dynamics", "Survival", "Claustrophobic"],
    },
    {
        "name": "Mafia Romance",
        "parents": ["Relationship Dynamics", "Systemic/Societal Conflict"],
    },
    {"name": "Monster Romance", "parents": ["Relationship Dynamics", "Reality"]},
    {"name": "Slow Burn", "parents": ["Relationship Dynamics", "Memory & Time"]},
    {
        "name": "Second Chance Romance",
        "parents": ["Relationship Dynamics", "Memory & Time", "Grief/Loss"],
    },
    # Character archetypes
    {"name": "Morally Grey", "parents": ["Anti-Hero"]},
    {
        "name": "Possessive Hero",
        "parents": ["Character Archetypes & Dynamics", "Obsession"],
    },
    {"name": "Cinnamon Roll", "parents": ["Character Archetypes & Dynamics"]},
    {"name": "Chosen One", "parents": ["Character Archetypes & Dynamics", "Quests"]},
    # ── Romance Genre Registers (v2.0) ───────────────────────────────────
    # Subgenre classification nodes. Placed AFTER their parents (Relationship
    # Dynamics, Historical, Reality, etc.) and BEFORE trope children that
    # reference them (Bully Romance → Dark Romance).
    {"name": "Dark Romance", "parents": ["Relationship Dynamics", "Thematic Core"]},
    {"name": "Contemporary Romance", "parents": ["Relationship Dynamics", "Grounded"]},
    {"name": "Romantic Fantasy", "parents": ["Relationship Dynamics", "Reality"]},
    {"name": "Historical Romance", "parents": ["Relationship Dynamics", "Historical"]},
    {"name": "Paranormal Romance", "parents": ["Relationship Dynamics", "Reality"]},
    {"name": "Sports Romance", "parents": ["Relationship Dynamics", "Grounded"]},
    {"name": "Workplace Romance", "parents": ["Relationship Dynamics", "Grounded"]},
    {"name": "MM Romance", "parents": ["Relationship Dynamics"]},
    {"name": "FF Romance", "parents": ["Relationship Dynamics"]},
    {"name": "Queer Romance", "parents": ["Relationship Dynamics"]},
    {"name": "Cozy Romance", "parents": ["Relationship Dynamics"]},
    {"name": "Romantic Comedy", "parents": ["Relationship Dynamics"]},
    # ── Romance Trope Nodes (v2.0) ───────────────────────────────────────
    # Topologically clean: all parents (Relationship Dynamics, Forbidden Romance,
    # Forced Proximity, Possessive Hero, Dark Romance, Enemies to Lovers, etc.)
    # are defined above.
    {"name": "Fake Dating", "parents": ["Relationship Dynamics"]},
    {"name": "Friends to Lovers", "parents": ["Relationship Dynamics"]},
    {"name": "Surprise Pregnancy", "parents": ["Relationship Dynamics"]},
    {"name": "Age Gap Romance", "parents": ["Forbidden Romance"]},
    {"name": "Billionaire Romance", "parents": ["Relationship Dynamics"]},
    {
        "name": "Small Town Romance",
        "parents": ["Setting & Environment", "Relationship Dynamics"],
    },
    {
        "name": "Holiday Romance",
        "parents": ["Setting & Environment", "Relationship Dynamics"],
    },
    {"name": "Instalove", "parents": ["Relationship Dynamics"]},
    {
        "name": "Love Triangle",
        "parents": ["Relationship Dynamics", "Interpersonal Conflict"],
    },
    {"name": "Hurt/Comfort", "parents": ["Relationship Dynamics", "Grief/Loss"]},
    {"name": "Bodyguard Romance", "parents": ["Forced Proximity"]},
    {"name": "Roommate Romance", "parents": ["Forced Proximity"]},
    {"name": "Single Parent Romance", "parents": ["Relationship Dynamics"]},
    {"name": "Touch Her and Die", "parents": ["Possessive Hero"]},
    {"name": "Brothers Best Friend", "parents": ["Forbidden Romance"]},
    # Dark-romance-specific (parents: Dark Romance + existing tropes)
    {"name": "Bully Romance", "parents": ["Enemies to Lovers", "Dark Romance"]},
    {"name": "Stalker Romance", "parents": ["Obsession", "Dark Romance"]},
    {"name": "Dark Reverse Harem", "parents": ["Reverse Harem", "Dark Romance"]},
    # ── Plot / Horror (unchanged) ────────────────────────────────────────
    {
        "name": "Heists",
        "parents": ["Plot Catalysts & Structures", "Systemic/Societal Conflict"],
    },
    {
        "name": "Rebellions",
        "parents": ["Systemic/Societal Conflict", "Plot Catalysts & Structures"],
    },
    {
        "name": "Tournaments/Death Games",
        "parents": ["Survival", "Plot Catalysts & Structures"],
    },
    {"name": "Whodunit", "parents": ["Mysteries"]},
    {"name": "Locked Room Mystery", "parents": ["Whodunit", "Claustrophobic"]},
    {
        "name": "Psychological Horror",
        "parents": ["Internal Conflict", "Unreliable Narrator"],
    },
    {"name": "Body Horror", "parents": ["Survival/External", "Reality"]},
    {
        "name": "Folk Horror",
        "parents": ["Isolated Institution", "Systemic/Societal Conflict"],
    },
    {"name": "Cosmic Horror", "parents": ["Cosmic/Lovecraftian", "Existentialism"]},
    # ── Fantasy Genre Registers (v3.0) ───────────────────────────────────────
    {"name": "High Fantasy", "parents": ["Epic", "Reality"]},
    {"name": "Urban Fantasy", "parents": ["Reality", "Grounded"]},
    {"name": "Low Fantasy", "parents": ["Reality", "Grounded"]},
    {"name": "Dark Fantasy", "parents": ["Reality", "Obsession"]},
    {"name": "Grimdark", "parents": ["Dark Fantasy", "War & Its Aftermath"]},
    {"name": "Cozy Fantasy", "parents": ["Reality", "Found Family Formation"]},
    {"name": "Romantasy", "parents": ["Reality", "Relationship Dynamics"]},
    {"name": "Fairy Tale Retelling", "parents": ["Reality", "Historical"]},
    {"name": "Sword & Sorcery", "parents": ["Epic", "Anti-Hero"]},
    {"name": "Gaslamp Fantasy", "parents": ["Historical", "Reality"]},
    {"name": "Science Fantasy", "parents": ["Reality", "Hard Sci-Fi"]},
    {"name": "Wuxia", "parents": ["Historical", "Epic"]},
    # Fantasy plot/character nodes
    {"name": "Court Intrigue", "parents": ["Systemic/Societal Conflict", "Quests"]},
    {"name": "Secret Heir", "parents": ["Chosen One", "Court Intrigue"]},
    {"name": "Reluctant Hero", "parents": ["Chosen One", "Internal Conflict"]},
    {
        "name": "Ancient Evil",
        "parents": ["Cosmic/Lovecraftian", "Plot Catalysts & Structures"],
    },
    {"name": "Reincarnation", "parents": ["Memory & Time", "Reality"]},
    {
        "name": "Forced Alliance",
        "parents": ["Interpersonal Conflict", "Plot Catalysts & Structures"],
    },
    {"name": "Prophecy", "parents": ["Chosen One", "Plot Catalysts & Structures"]},
    {"name": "Gods and Mortals", "parents": ["Cosmic/Lovecraftian", "Thematic Core"]},
    {
        "name": "Rivals to Lovers",
        "parents": ["Enemies to Lovers", "Relationship Dynamics"],
    },
    {"name": "Band of Misfits", "parents": ["Found Family Formation", "Anti-Hero"]},
    {"name": "Fae Courts", "parents": ["Court Intrigue", "Reality"]},
    {"name": "Dragon Riders", "parents": ["Epic", "Quests"]},
    # ── Fantasy subgenre refinements (v3.1) ────────────────────────────────
    {"name": "Progression Fantasy", "parents": ["Reality", "Quests"]},
    {"name": "Academy Fantasy", "parents": ["Isolated Institution", "Reality"]},
    {"name": "Military Fantasy", "parents": ["War & Its Aftermath", "Epic"]},
    {
        "name": "Political Fantasy",
        "parents": ["Court Intrigue", "Systemic/Societal Conflict"],
    },
    {"name": "Kingdom Building", "parents": ["Epic", "Systemic/Societal Conflict"]},
    {"name": "Monster Hunting", "parents": ["Survival/External", "Quests"]},
    {"name": "Pirate Fantasy", "parents": ["Epic", "Heists"]},
    {"name": "Time Loop", "parents": ["Memory & Time", "Reality"]},
    {"name": "Magical Competition", "parents": ["Tournaments/Death Games", "Reality"]},
    # Thriller Genre Registers (v5.0)
    {"name": "Mystery Fiction", "parents": ["Mysteries", "Grounded"]},
    {"name": "Psychological Thriller", "parents": ["Mysteries", "Internal Conflict"]},
    {"name": "Domestic Thriller", "parents": ["Mysteries", "Grounded"]},
    {"name": "Crime Thriller", "parents": ["Mysteries", "Systemic/Societal Conflict"]},
    {"name": "Legal Thriller", "parents": ["Mysteries", "Systemic/Societal Conflict"]},
    {"name": "Spy Thriller", "parents": ["Mysteries", "War & Its Aftermath"]},
    {
        "name": "Police Procedural",
        "parents": ["Mysteries", "Systemic/Societal Conflict"],
    },
    {"name": "Serial Killer Thriller", "parents": ["Mysteries", "Obsession"]},
    {"name": "Noir", "parents": ["Mysteries", "Anti-Hero"]},
    {"name": "Political Thriller", "parents": ["Mysteries", "Corruption of Power"]},
    {"name": "Action Thriller", "parents": ["Mysteries", "Survival"]},
    {"name": "Cozy Mystery", "parents": ["Mystery Fiction", "Mysteries", "Grounded"]},
    # Thriller Trope Nodes (v5.0)
    {
        "name": "Cat and Mouse",
        "parents": ["Psychological Thriller", "Interpersonal Conflict"],
    },
    {
        "name": "Conspiracy",
        "parents": ["Systemic/Societal Conflict", "Political Thriller"],
    },
    {
        "name": "Race Against Time",
        "parents": ["Plot Catalysts & Structures", "Action Thriller"],
    },
    {"name": "Gaslighting", "parents": ["Internal Conflict", "Psychological Thriller"]},
    {"name": "Stalking", "parents": ["Obsession", "Psychological Thriller"]},
    {"name": "Amnesia", "parents": ["Memory & Time", "Internal Conflict"]},
    {"name": "Missing Person", "parents": ["Mysteries", "Grief/Loss"]},
    {
        "name": "Cover-Up",
        "parents": ["Systemic/Societal Conflict", "Corruption of Power"],
    },
    {
        "name": "Twist Ending",
        "parents": ["Plot Catalysts & Structures", "Unreliable Narrator"],
    },
    {
        "name": "Everyone Is a Suspect",
        "parents": ["Mysteries", "Interpersonal Conflict"],
    },
    {"name": "Red Herring", "parents": ["Mysteries", "Plot Catalysts & Structures"]},
    {"name": "Cold Case", "parents": ["Mysteries", "Memory & Time"]},
    {
        "name": "Vigilante Justice",
        "parents": ["Anti-Hero", "Systemic/Societal Conflict"],
    },
    {
        "name": "Wrongfully Accused",
        "parents": ["Systemic/Societal Conflict", "Survival"],
    },
    {
        "name": "Killer POV",
        "parents": ["Unreliable Narrator", "Serial Killer Thriller"],
    },
    # ── Structural Archetypes (v5.1) ─────────────────────────────────────
    {
        "name": "Dual Timeline",
        "parents": ["Plot Catalysts & Structures", "Memory & Time"],
    },
    {
        "name": "Single POV",
        "parents": ["Plot Catalysts & Structures", "Internal Conflict"],
    },
    {
        "name": "Multi-POV Structure",
        "parents": ["Plot Catalysts & Structures", "Interpersonal Conflict"],
    },
    {"name": "Epistolary", "parents": ["Plot Catalysts & Structures", "Memory & Time"]},
    {
        "name": "Reverse Timeline",
        "parents": ["Plot Catalysts & Structures", "Memory & Time"],
    },
    {
        "name": "Nonlinear Narrative",
        "parents": ["Plot Catalysts & Structures", "Memory & Time"],
    },
    # ── Tone Axis (v5.1) ─────────────────────────────────────────────────
    {"name": "Dark Tone", "parents": ["Thematic Core", "Internal Conflict"]},
    {"name": "Light Tone", "parents": ["Thematic Core", "Grounded"]},
    {"name": "Stylized", "parents": ["Reality", "Thematic Core"]},
    {"name": "Mind-Bending", "parents": ["Reality", "Internal Conflict"]},
    {"name": "Cold/Clinical", "parents": ["Thematic Core", "Unreliable Narrator"]},
    # ── Emotional Drivers (v5.1) ──────────────────────────────────────────
    {"name": "Paranoia", "parents": ["Internal Conflict", "Psychological Thriller"]},
    {"name": "Guilt", "parents": ["Internal Conflict", "Grief/Loss"]},
    {"name": "Revenge", "parents": ["Internal Conflict", "Systemic/Societal Conflict"]},
    {
        "name": "Fear of Exposure",
        "parents": ["Internal Conflict", "Psychological Thriller"],
    },
    {"name": "Moral Ambiguity", "parents": ["Anti-Hero", "Internal Conflict"]},
    # ── Horror Subgenre Registers (v6.0) ───────────────────────────────────
    {"name": "Gothic Horror", "parents": ["Psychological Horror", "Historical"]},
    {"name": "Supernatural Horror", "parents": ["Reality", "Cosmic/Lovecraftian"]},
    {
        "name": "Haunted House",
        "parents": ["Isolated Institution", "Supernatural Horror"],
    },
    {"name": "Weird Fiction", "parents": ["Cosmic/Lovecraftian", "Reality"]},
    {"name": "Quiet Horror", "parents": ["Psychological Horror", "Existentialism"]},
    {
        "name": "Domestic Horror",
        "parents": ["Psychological Horror", "Interpersonal Conflict"],
    },
    {"name": "Dread & Atmosphere", "parents": ["Psychological Horror"]},
    # ── Sci-Fi Subgenre Registers (v7.0) ──────────────────────────────────
    {"name": "First Contact", "parents": ["Hard Sci-Fi", "Cosmic/Lovecraftian"]},
    {"name": "Post-Apocalyptic", "parents": ["Future", "Survival/External"]},
    {"name": "AI & Consciousness", "parents": ["Man vs Technology", "Existentialism"]},
    {"name": "Generation Ship", "parents": ["Space Opera", "Survival/External"]},
    {
        "name": "Alien Civilization",
        "parents": ["Space Opera", "Colonialism/Post-Colonialism"],
    },
    {"name": "Time Travel", "parents": ["Future", "Memory & Time"]},
    {"name": "Parallel Universe", "parents": ["Reality", "Future"]},
    {"name": "Colony & Terraforming", "parents": ["Space Opera", "Survival"]},
    {"name": "Near-Future", "parents": ["Future", "Grounded"]},
    {"name": "Far-Future", "parents": ["Future", "Epic"]},
    {"name": "Biotech Sci-Fi", "parents": ["Hard Sci-Fi", "Body Horror"]},
    {"name": "Space Exploration", "parents": ["Hard Sci-Fi", "Quests"]},
    {"name": "Corporate Dystopia", "parents": ["Dystopia", "Cyberpunk"]},
    {"name": "Solarpunk", "parents": ["Future", "Systemic/Societal Conflict"]},
    {"name": "Cli-Fi", "parents": ["Future", "Survival/External"]},
    {"name": "Space Western", "parents": ["Space Opera", "Anti-Hero"]},
    # Sci-Fi tone/experience nodes
    {"name": "Hard Science Thriller", "parents": ["Hard Sci-Fi", "Mysteries"]},
    {
        "name": "Speculative Philosophical Sci-Fi",
        "parents": ["Hard Sci-Fi", "Existentialism"],
    },
    {"name": "Action-Driven Sci-Fi", "parents": ["Space Opera", "Military Sci-Fi"]},
    {"name": "Biopunk", "parents": ["Hard Sci-Fi", "Body Horror"]},
    {"name": "Uplift", "parents": ["Hard Sci-Fi", "Systemic/Societal Conflict"]},
    {"name": "Retrofuturism", "parents": ["Future", "Historical"]},
    {"name": "Quantum Sci-Fi", "parents": ["Hard Sci-Fi", "Reality"]},
    {"name": "Utopian Sci-Fi", "parents": ["Future", "Systemic/Societal Conflict"]},
    {"name": "Post-Scarcity Sci-Fi", "parents": ["Future", "Utopian Sci-Fi"]},
    {
        "name": "Totalitarian Sci-Fi",
        "parents": ["Dystopia", "Systemic/Societal Conflict"],
    },
    # Literary Fiction Nodes (v8.0)
    {"name": "Literary Fiction", "parents": ["Thematic Core", "Grounded"]},
    {"name": "Autofiction", "parents": ["Literary Fiction", "Identity/Self-Discovery"]},
    {
        "name": "Postcolonial Literature",
        "parents": ["Literary Fiction", "Colonialism/Post-Colonialism"],
    },
    {
        "name": "Magical Realism Literary",
        "parents": ["Literary Fiction", "Magical Realism"],
    },
    {"name": "Modernist Literature", "parents": ["Literary Fiction", "Existentialism"]},
    {"name": "Absurdist Fiction", "parents": ["Literary Fiction", "Existentialism"]},
    {"name": "Epistolary Novel", "parents": ["Literary Fiction", "Memory & Time"]},
    {
        "name": "Stream of Consciousness",
        "parents": ["Literary Fiction", "Internal Conflict"],
    },
    {"name": "Campus Novel", "parents": ["Literary Fiction", "Isolated Institution"]},
    {
        "name": "Bildungsroman",
        "parents": ["Literary Fiction", "Identity/Self-Discovery"],
    },
    {"name": "Family Saga", "parents": ["Literary Fiction", "Memory & Time"]},
    {
        "name": "Immigrant Narrative",
        "parents": ["Literary Fiction", "Colonialism/Post-Colonialism"],
    },
    {"name": "War Literature", "parents": ["Literary Fiction", "War & Its Aftermath"]},
    {
        "name": "Protest Literature",
        "parents": ["Literary Fiction", "Systemic/Societal Conflict"],
    },
    {
        "name": "Historical Literary Fiction",
        "parents": ["Literary Fiction", "Historical"],
    },
    {"name": "Experimental Fiction", "parents": ["Literary Fiction"]},
    {"name": "Literary Noir", "parents": ["Literary Fiction", "Moral Ambiguity"]},
    {"name": "Literary Tragedy", "parents": ["Literary Fiction", "Grief/Loss"]},
    {"name": "Quiet Fiction", "parents": ["Literary Fiction", "Existentialism"]},
    {"name": "Lyrical Prose", "parents": ["Literary Fiction", "Thematic Core"]},
    {"name": "Metafiction", "parents": ["Literary Fiction", "Reality"]},
    {"name": "Death & Mortality", "parents": ["Literary Fiction", "Grief/Loss"]},
    {
        "name": "Alienation & Isolation",
        "parents": ["Literary Fiction", "Internal Conflict"],
    },
    # Non-Fiction Nodes (v9.0)
    {"name": "Nonfiction", "parents": ["Thematic Core", "Grounded"]},
    {"name": "Narrative Nonfiction", "parents": ["Nonfiction", "Grounded"]},
    {"name": "Non-Narrative Nonfiction", "parents": ["Nonfiction"]},
    {"name": "Memoir", "parents": ["Narrative Nonfiction", "Identity/Self-Discovery"]},
    {"name": "Autobiography", "parents": ["Memoir"]},
    {"name": "True Crime Narrative", "parents": ["Narrative Nonfiction", "Mysteries"]},
    {
        "name": "Investigative Journalism",
        "parents": ["Narrative Nonfiction", "Systemic/Societal Conflict"],
    },
    {"name": "Travel Writing", "parents": ["Narrative Nonfiction", "Quests"]},
    {
        "name": "Nature Writing",
        "parents": ["Narrative Nonfiction", "Survival/External"],
    },
    {"name": "War Memoir", "parents": ["Memoir", "War & Its Aftermath"]},
    {"name": "Essays", "parents": ["Narrative Nonfiction", "Thematic Core"]},
    {"name": "Literary Journalism", "parents": ["Investigative Journalism", "Essays"]},
    {"name": "History", "parents": ["Non-Narrative Nonfiction", "War & Its Aftermath"]},
    {"name": "Philosophy", "parents": ["Non-Narrative Nonfiction", "Existentialism"]},
    {"name": "Popular Science", "parents": ["Non-Narrative Nonfiction", "Hard Sci-Fi"]},
    {
        "name": "Self-Help",
        "parents": ["Non-Narrative Nonfiction", "Identity/Self-Discovery"],
    },
    {
        "name": "Biography",
        "parents": ["Narrative Nonfiction", "Non-Narrative Nonfiction"],
    },
    {
        "name": "Psychology",
        "parents": ["Non-Narrative Nonfiction", "Internal Conflict"],
    },
    {
        "name": "Sociology",
        "parents": ["Non-Narrative Nonfiction", "Systemic/Societal Conflict"],
    },
    {"name": "Economics", "parents": ["Non-Narrative Nonfiction", "Class Struggle"]},
    {
        "name": "Political Theory",
        "parents": ["Non-Narrative Nonfiction", "Systemic/Societal Conflict"],
    },
    {
        "name": "Cultural Criticism",
        "parents": ["Non-Narrative Nonfiction", "Thematic Core"],
    },
    # Historical Fiction Nodes (v10.0)
    # Setting-period nodes
    {"name": "Ancient World", "parents": ["Timeline"]},
    {"name": "Medieval World", "parents": ["Timeline"]},
    # Genre registers — by period
    {
        "name": "Historical Fiction",
        "parents": ["Literary Fiction", "Historical"],
    },
    {
        "name": "Ancient Historical Fiction",
        "parents": ["Historical Fiction", "Ancient World"],
    },
    {
        "name": "Medieval Historical Fiction",
        "parents": ["Historical Fiction", "Medieval World"],
    },
    {
        "name": "Victorian Fiction",
        "parents": ["Historical Fiction", "Gothic Horror"],
    },
    # By form/style — Epic = scale only
    {"name": "Historical Epic", "parents": ["Historical Fiction", "Epic"]},
    {
        "name": "Historical Mystery",
        "parents": ["Historical Fiction", "Mystery Fiction", "Mysteries"],
    },
    {
        "name": "Historical Thriller",
        "parents": ["Historical Fiction", "Psychological Horror"],
    },
    {"name": "Historical Adventure", "parents": ["Historical Fiction", "Quests"]},
    {
        "name": "War Fiction",
        "parents": ["Historical Fiction", "War & Its Aftermath"],
    },
    {
        "name": "Biographical Fiction",
        "parents": ["Historical Fiction", "Literary Fiction"],
    },
    {
        "name": "Alternate History Fiction",
        "parents": ["Historical Fiction", "Alternate History"],
    },
    {
        "name": "Gaslamp Fiction",
        "parents": ["Historical Fiction", "Gaslamp Fantasy"],
    },
    # Cross-genre registers
    {
        "name": "Colonial Historical Fiction",
        "parents": ["Historical Fiction", "Colonialism/Post-Colonialism"],
    },
    {
        "name": "Postcolonial Historical Fiction",
        "parents": ["Historical Fiction", "Colonialism/Post-Colonialism"],
    },
    {
        "name": "Rural Historical Fiction",
        "parents": ["Historical Fiction", "Class Struggle"],
    },
    {
        "name": "Western Fiction",
        "parents": ["Historical Fiction", "Survival/External"],
    },
    {
        "name": "Historical Bildungsroman",
        "parents": ["Historical Fiction", "Bildungsroman"],
    },
    {
        "name": "Political Historical Fiction",
        "parents": ["Historical Fiction", "Systemic/Societal Conflict"],
    },
    {
        "name": "Experimental Historical Fiction",
        "parents": ["Historical Fiction", "Experimental Fiction"],
    },
    # Regional registers — single-parent for clean geo signal
    {"name": "African Historical Fiction", "parents": ["Historical Fiction"]},
    {"name": "Asian Historical Fiction", "parents": ["Historical Fiction"]},
    {"name": "European Historical Fiction", "parents": ["Historical Fiction"]},
    {
        "name": "Middle Eastern Historical Fiction",
        "parents": ["Historical Fiction"],
    },
    # Mystery Fiction Refinements (v11.0)
    {"name": "Crime", "parents": ["Thematic Core"]},
    {"name": "Amateur Sleuth", "parents": ["Mystery Fiction", "Whodunit"]},
    {"name": "Hardboiled Detective", "parents": ["Mystery Fiction", "Anti-Hero"]},
    {
        "name": "Classic Detective Fiction",
        "parents": ["Mystery Fiction", "Whodunit"],
    },
    {
        "name": "Nordic Noir",
        "parents": ["Mystery Fiction", "Psychological Horror"],
    },
    {
        "name": "Psychological Mystery",
        "parents": ["Mystery Fiction", "Psychological Thriller"],
    },
    {
        "name": "Techno-Mystery",
        "parents": ["Mystery Fiction", "Man vs Technology"],
    },
    {"name": "Small Town Mystery", "parents": ["Cozy Mystery"]},
    {
        "name": "Domestic Cozy Mystery",
        "parents": ["Cozy Mystery", "Domestic Thriller"],
    },
    {"name": "Animal Cozy Mystery", "parents": ["Cozy Mystery"]},
    {"name": "Courtroom Mystery", "parents": ["Legal Thriller", "Whodunit"]},
    {"name": "Puzzle Mystery", "parents": ["Whodunit"]},
    # Nonfiction / Memoir Refinements (v11.0)
    {
        "name": "Coming of Age Memoir",
        "parents": ["Memoir", "Bildungsroman"],
    },
    {"name": "Trauma Memoir", "parents": ["Memoir", "Grief/Loss"]},
    {
        "name": "Political Memoir",
        "parents": ["Memoir", "Systemic/Societal Conflict"],
    },
    {
        "name": "Creative Nonfiction",
        "parents": ["Memoir", "Literary Fiction"],
    },
    {"name": "Celebrity Biography", "parents": ["Biography"]},
    {
        "name": "Literary Biography",
        "parents": ["Biography", "Literary Fiction"],
    },
    {
        "name": "Investigative Nonfiction",
        "parents": ["Narrative Nonfiction", "Systemic/Societal Conflict"],
    },
    {
        "name": "True Crime",
        "parents": ["Narrative Nonfiction", "Mysteries"],
    },
    {"name": "Scientific Memoir", "parents": ["Memoir", "Popular Science"]},
]
