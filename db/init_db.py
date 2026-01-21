import asyncpg
import asyncio
import logging
from utils import *

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - DB - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def ensure_tables():
    conn = await asyncpg.connect("postgresql://AVATAR:password@db:5432/AVATAR")

    # --- ServerConfig table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS ServerConfig (
        guild_id BIGINT PRIMARY KEY,
        default_limit SMALLINT,
        letter_delay BIGINT,
        category_id BIGINT,
        reset_time TIME,
        admin_response_channel_id BIGINT
    );
    """)

    # Ensure all expected columns exist
    await conn.execute("ALTER TABLE ServerConfig ADD COLUMN IF NOT EXISTS default_limit SMALLINT;")
    await conn.execute("ALTER TABLE ServerConfig ADD COLUMN IF NOT EXISTS letter_delay BIGINT;")
    await conn.execute("ALTER TABLE ServerConfig ADD COLUMN IF NOT EXISTS category_id BIGINT;")
    await conn.execute("ALTER TABLE ServerConfig ADD COLUMN IF NOT EXISTS reset_time TIME;")
    await conn.execute("ALTER TABLE ServerConfig ADD COLUMN IF NOT EXISTS admin_response_channel_id BIGINT;")

    # --- Character table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS Character (
        id SERIAL PRIMARY KEY,
        identifier TEXT NOT NULL,
        name TEXT NOT NULL,
        user_id BIGINT,
        channel_id BIGINT NOT NULL,
        letter_limit SMALLINT,
        letter_count SMALLINT NOT NULL DEFAULT 0,
        guild_id BIGINT NOT NULL
    );
    """)

    # --- Column Synchronization ---

    # Ensure all expected columns exist
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS identifier TEXT;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS name TEXT;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS user_id BIGINT;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS channel_id BIGINT;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS letter_limit SMALLINT;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS letter_count SMALLINT DEFAULT 0;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS guild_id BIGINT;")
    # Resource production per turn
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS ore_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS lumber_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS coal_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS rations_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS cloth_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS platinum_production INTEGER DEFAULT 0;")
    # Victory points
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS victory_points INTEGER DEFAULT 0;")

    # Multi-faction representation support
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS represented_faction_id INTEGER;")
    await conn.execute("ALTER TABLE Character ADD COLUMN IF NOT EXISTS representation_changed_turn INTEGER;")

    # --- Constraint Synchronization ---
    # Unique constraint on (identifier, guild_id)
    await conn.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'unique_identifier_per_guild'
        ) THEN
            ALTER TABLE Character
            ADD CONSTRAINT unique_identifier_per_guild UNIQUE (identifier, guild_id);
        END IF;
    END$$;
    """)

    # --- Alias table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS Alias (
        id SERIAL PRIMARY KEY,
        character_id INTEGER NOT NULL REFERENCES Character(id) ON DELETE CASCADE,
        alias TEXT NOT NULL,
        guild_id BIGINT NOT NULL,
        UNIQUE (alias, guild_id)
    );
    """)

    # Ensure all expected columns exist
    await conn.execute("ALTER TABLE Alias ADD COLUMN IF NOT EXISTS character_id INTEGER;")
    await conn.execute("ALTER TABLE Alias ADD COLUMN IF NOT EXISTS alias TEXT;")
    await conn.execute("ALTER TABLE Alias ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # Foreign key constraint linking guild_id -> ServerConfig.guild_id
    await conn.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'character_guild_id_fkey'
        ) THEN
            ALTER TABLE Character
            ADD CONSTRAINT character_guild_id_fkey
            FOREIGN KEY (guild_id) REFERENCES ServerConfig (guild_id);
        END IF;
    END$$;
    """)

    await conn.execute("""
    CREATE TABLE IF NOT EXISTS HawkyTask (
        id SERIAL PRIMARY KEY,
        task TEXT NOT NULL,
        recipient_identifier TEXT,
        sender_identifier TEXT,
        parameter TEXT,
        scheduled_time TIMESTAMP,
        guild_int BIGINT NOT NULL
    );
    """)

    # --- Ensure hawky_tasks columns match the desired schema ---
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS id SERIAL PRIMARY KEY;")
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS task TEXT NOT NULL;")
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS recipient_identifier TEXT;")
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS sender_identifier TEXT;")
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS parameter TEXT;")
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS scheduled_time TIMESTAMP;")
    await conn.execute("ALTER TABLE HawkyTask ADD COLUMN IF NOT EXISTS guild_id BIGINT NOT NULL;")

    # --- SentLetter table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS SentLetter (
        id SERIAL PRIMARY KEY,
        message_id BIGINT NOT NULL,
        channel_id BIGINT NOT NULL,
        sender_identifier TEXT NOT NULL,
        recipient_identifier TEXT NOT NULL,
        original_message_channel_id BIGINT NOT NULL,
        original_message_id BIGINT NOT NULL,
        has_response BOOLEAN NOT NULL DEFAULT FALSE,
        guild_id BIGINT NOT NULL,
        sent_time TIMESTAMP NOT NULL
    );
    """)

    # --- Ensure SentLetter columns match the desired schema ---
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS id SERIAL PRIMARY KEY;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS message_id BIGINT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS channel_id BIGINT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS sender_identifier TEXT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS recipient_identifier TEXT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS original_message_channel_id BIGINT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS original_message_id BIGINT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS has_response BOOLEAN DEFAULT FALSE;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS guild_id BIGINT NOT NULL;")
    await conn.execute("ALTER TABLE SentLetter ADD COLUMN IF NOT EXISTS sent_time TIMESTAMP NOT NULL;")

    # --- WARGAME TABLES ---

    # --- Territory table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS Territory (
        id SERIAL PRIMARY KEY,
        territory_id VARCHAR(50) NOT NULL,
        name VARCHAR(255),
        terrain_type VARCHAR(50) NOT NULL,
        ore_production INTEGER DEFAULT 0,
        lumber_production INTEGER DEFAULT 0,
        coal_production INTEGER DEFAULT 0,
        rations_production INTEGER DEFAULT 0,
        cloth_production INTEGER DEFAULT 0,
        platinum_production INTEGER DEFAULT 0,
        controller_character_id INTEGER REFERENCES Character(id) ON DELETE SET NULL,
        original_nation VARCHAR(50),
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(territory_id, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS territory_id VARCHAR(50);")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS name VARCHAR(255);")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS terrain_type VARCHAR(50);")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS ore_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS lumber_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS coal_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS rations_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS cloth_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS platinum_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS controller_character_id INTEGER;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS original_nation VARCHAR(50);")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS guild_id BIGINT;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS victory_points INTEGER DEFAULT 0;")

    # Add controller_faction_id for faction ownership of territories
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS controller_faction_id INTEGER;")

    # Migration: Change territory_id from INTEGER to VARCHAR(50) for existing databases
    await conn.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'territory' AND column_name = 'territory_id' AND data_type = 'integer'
            ) THEN
                ALTER TABLE Territory ALTER COLUMN territory_id TYPE VARCHAR(50) USING territory_id::VARCHAR;
            END IF;
        END $$;
    """)

    # Add index for controller_character_id
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_territory_controller
    ON Territory(controller_character_id, guild_id);
    """)

    # Add index for controller_faction_id
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_territory_faction_controller
    ON Territory(controller_faction_id, guild_id);
    """)

    # --- Faction table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS Faction (
        id SERIAL PRIMARY KEY,
        faction_id VARCHAR(50) NOT NULL,
        name VARCHAR(255) NOT NULL,
        leader_character_id INTEGER REFERENCES Character(id) ON DELETE SET NULL,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(faction_id, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS faction_id VARCHAR(50);")
    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS name VARCHAR(255);")
    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS leader_character_id INTEGER;")
    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS created_turn INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS has_declared_war BOOLEAN DEFAULT FALSE;")
    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS guild_id BIGINT;")
    # Resource spending per turn (deducted during upkeep phase)
    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS ore_spending INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS lumber_spending INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS coal_spending INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS rations_spending INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS cloth_spending INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS platinum_spending INTEGER DEFAULT 0;")
    # Nation identifier for faction (e.g., 'fire-nation', 'earth-kingdom')
    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS nation VARCHAR(50);")

    # --- FactionMember table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS FactionMember (
        id SERIAL PRIMARY KEY,
        faction_id INTEGER NOT NULL REFERENCES Faction(id) ON DELETE CASCADE,
        character_id INTEGER NOT NULL REFERENCES Character(id) ON DELETE CASCADE,
        joined_turn INTEGER NOT NULL,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE
    );
    """)

    # Migration: Change FactionMember constraint from single-faction to multi-faction
    # Remove old single-faction constraint if it exists, add new multi-faction constraint
    await conn.execute("""
    DO $$
    BEGIN
        -- Drop old single-faction constraint if it exists
        IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'factionmember_character_id_guild_id_key'
        ) THEN
            ALTER TABLE FactionMember DROP CONSTRAINT factionmember_character_id_guild_id_key;
        END IF;

        -- Add new multi-faction constraint if it doesn't exist
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'factionmember_faction_character_guild_key'
        ) THEN
            ALTER TABLE FactionMember ADD CONSTRAINT factionmember_faction_character_guild_key
                UNIQUE(faction_id, character_id, guild_id);
        END IF;
    END$$;
    """)

    await conn.execute("ALTER TABLE FactionMember ADD COLUMN IF NOT EXISTS faction_id INTEGER;")
    await conn.execute("ALTER TABLE FactionMember ADD COLUMN IF NOT EXISTS character_id INTEGER;")
    await conn.execute("ALTER TABLE FactionMember ADD COLUMN IF NOT EXISTS joined_turn INTEGER;")
    await conn.execute("ALTER TABLE FactionMember ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # --- FactionResources table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS FactionResources (
        id SERIAL PRIMARY KEY,
        faction_id INTEGER NOT NULL REFERENCES Faction(id) ON DELETE CASCADE,
        ore INTEGER DEFAULT 0,
        lumber INTEGER DEFAULT 0,
        coal INTEGER DEFAULT 0,
        rations INTEGER DEFAULT 0,
        cloth INTEGER DEFAULT 0,
        platinum INTEGER DEFAULT 0,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(faction_id, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE FactionResources ADD COLUMN IF NOT EXISTS faction_id INTEGER;")
    await conn.execute("ALTER TABLE FactionResources ADD COLUMN IF NOT EXISTS ore INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE FactionResources ADD COLUMN IF NOT EXISTS lumber INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE FactionResources ADD COLUMN IF NOT EXISTS coal INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE FactionResources ADD COLUMN IF NOT EXISTS rations INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE FactionResources ADD COLUMN IF NOT EXISTS cloth INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE FactionResources ADD COLUMN IF NOT EXISTS platinum INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE FactionResources ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # --- FactionPermission table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS FactionPermission (
        id SERIAL PRIMARY KEY,
        faction_id INTEGER NOT NULL REFERENCES Faction(id) ON DELETE CASCADE,
        character_id INTEGER NOT NULL REFERENCES Character(id) ON DELETE CASCADE,
        permission_type VARCHAR(20) NOT NULL,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(faction_id, character_id, permission_type, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE FactionPermission ADD COLUMN IF NOT EXISTS faction_id INTEGER;")
    await conn.execute("ALTER TABLE FactionPermission ADD COLUMN IF NOT EXISTS character_id INTEGER;")
    await conn.execute("ALTER TABLE FactionPermission ADD COLUMN IF NOT EXISTS permission_type VARCHAR(20);")
    await conn.execute("ALTER TABLE FactionPermission ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # Create index for FactionPermission lookups
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_faction_permission_lookup
        ON FactionPermission(faction_id, permission_type, guild_id);
    """)

    # --- Unit table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS Unit (
        id SERIAL PRIMARY KEY,
        unit_id VARCHAR(50) NOT NULL,
        name VARCHAR(255),
        unit_type VARCHAR(50) NOT NULL,
        owner_character_id INTEGER NOT NULL REFERENCES Character(id) ON DELETE CASCADE,
        commander_character_id INTEGER REFERENCES Character(id) ON DELETE SET NULL,
        commander_assigned_turn INTEGER,
        faction_id INTEGER REFERENCES Faction(id) ON DELETE SET NULL,
        movement INTEGER NOT NULL DEFAULT 1,
        organization INTEGER NOT NULL,
        max_organization INTEGER NOT NULL,
        attack INTEGER NOT NULL DEFAULT 0,
        defense INTEGER NOT NULL DEFAULT 0,
        siege_attack INTEGER NOT NULL DEFAULT 0,
        siege_defense INTEGER NOT NULL DEFAULT 0,
        size INTEGER DEFAULT 1,
        capacity INTEGER DEFAULT 0,
        current_territory_id VARCHAR(50),
        is_naval BOOLEAN DEFAULT FALSE,
        upkeep_ore INTEGER DEFAULT 0,
        upkeep_lumber INTEGER DEFAULT 0,
        upkeep_coal INTEGER DEFAULT 0,
        upkeep_rations INTEGER DEFAULT 0,
        upkeep_cloth INTEGER DEFAULT 0,
        upkeep_platinum INTEGER DEFAULT 0,
        keywords TEXT[],
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(unit_id, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS unit_id VARCHAR(50);")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS name VARCHAR(255);")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS unit_type VARCHAR(50);")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS owner_character_id INTEGER;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS commander_character_id INTEGER;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS commander_assigned_turn INTEGER;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS faction_id INTEGER;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS movement INTEGER DEFAULT 1;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS organization INTEGER;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS max_organization INTEGER;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS attack INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS defense INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS siege_attack INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS siege_defense INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS size INTEGER DEFAULT 1;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS capacity INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS current_territory_id VARCHAR(50);")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS is_naval BOOLEAN DEFAULT FALSE;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS upkeep_ore INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS upkeep_lumber INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS upkeep_coal INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS upkeep_rations INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS upkeep_cloth INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS upkeep_platinum INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS keywords TEXT[];")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS guild_id BIGINT;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'ACTIVE';")

    # Add owner_faction_id for faction ownership of units
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS owner_faction_id INTEGER;")

    # Make owner_character_id nullable (units can now be owned by factions instead)
    await conn.execute("ALTER TABLE Unit ALTER COLUMN owner_character_id DROP NOT NULL;")

    # Migration: Change current_territory_id from INTEGER to VARCHAR(50) for existing databases
    await conn.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'unit' AND column_name = 'current_territory_id' AND data_type = 'integer'
            ) THEN
                ALTER TABLE Unit ALTER COLUMN current_territory_id TYPE VARCHAR(50) USING current_territory_id::VARCHAR;
            END IF;
        END $$;
    """)

    # Create index for faction-owned units
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_unit_owner_faction
        ON Unit(owner_faction_id, guild_id);
    """)

    # --- UnitType table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS UnitType (
        id SERIAL PRIMARY KEY,
        type_id VARCHAR(50) NOT NULL,
        name VARCHAR(255) NOT NULL,
        nation VARCHAR(50),
        movement INTEGER NOT NULL,
        organization INTEGER NOT NULL,
        attack INTEGER NOT NULL,
        defense INTEGER NOT NULL,
        siege_attack INTEGER NOT NULL,
        siege_defense INTEGER NOT NULL,
        size INTEGER DEFAULT 1,
        capacity INTEGER DEFAULT 0,
        is_naval BOOLEAN DEFAULT FALSE,
        keywords TEXT[],
        cost_ore INTEGER DEFAULT 0,
        cost_lumber INTEGER DEFAULT 0,
        cost_coal INTEGER DEFAULT 0,
        cost_rations INTEGER DEFAULT 0,
        cost_cloth INTEGER DEFAULT 0,
        cost_platinum INTEGER DEFAULT 0,
        upkeep_ore INTEGER DEFAULT 0,
        upkeep_lumber INTEGER DEFAULT 0,
        upkeep_coal INTEGER DEFAULT 0,
        upkeep_rations INTEGER DEFAULT 0,
        upkeep_cloth INTEGER DEFAULT 0,
        upkeep_platinum INTEGER DEFAULT 0,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(type_id, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS type_id VARCHAR(50);")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS name VARCHAR(255);")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS nation VARCHAR(50);")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS movement INTEGER;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS organization INTEGER;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS attack INTEGER;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS defense INTEGER;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS siege_attack INTEGER;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS siege_defense INTEGER;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS size INTEGER DEFAULT 1;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS capacity INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS is_naval BOOLEAN DEFAULT FALSE;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS keywords TEXT[];")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS cost_ore INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS cost_lumber INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS cost_coal INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS cost_rations INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS cost_cloth INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS cost_platinum INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS upkeep_ore INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS upkeep_lumber INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS upkeep_coal INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS upkeep_rations INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS upkeep_cloth INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS upkeep_platinum INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # Migrate unique constraint from (type_id, nation, guild_id) to (type_id, guild_id)
    await conn.execute("""
    DO $$
    BEGIN
        -- Drop old constraint if it exists
        IF EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'unittype_type_id_nation_guild_id_key'
        ) THEN
            ALTER TABLE UnitType DROP CONSTRAINT unittype_type_id_nation_guild_id_key;
        END IF;

        -- Add new constraint if it doesn't exist
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'unittype_type_id_guild_id_key'
        ) THEN
            ALTER TABLE UnitType ADD CONSTRAINT unittype_type_id_guild_id_key UNIQUE (type_id, guild_id);
        END IF;
    END$$;
    """)

    # --- BuildingType table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS BuildingType (
        id SERIAL PRIMARY KEY,
        type_id VARCHAR(50) NOT NULL,
        name VARCHAR(255) NOT NULL,
        description TEXT,
        cost_ore INTEGER DEFAULT 0,
        cost_lumber INTEGER DEFAULT 0,
        cost_coal INTEGER DEFAULT 0,
        cost_rations INTEGER DEFAULT 0,
        cost_cloth INTEGER DEFAULT 0,
        cost_platinum INTEGER DEFAULT 0,
        upkeep_ore INTEGER DEFAULT 0,
        upkeep_lumber INTEGER DEFAULT 0,
        upkeep_coal INTEGER DEFAULT 0,
        upkeep_rations INTEGER DEFAULT 0,
        upkeep_cloth INTEGER DEFAULT 0,
        upkeep_platinum INTEGER DEFAULT 0,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(type_id, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS type_id VARCHAR(50);")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS name VARCHAR(255);")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS description TEXT;")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS cost_ore INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS cost_lumber INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS cost_coal INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS cost_rations INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS cost_cloth INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS cost_platinum INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS upkeep_ore INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS upkeep_lumber INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS upkeep_coal INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS upkeep_rations INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS upkeep_cloth INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS upkeep_platinum INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE BuildingType ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # --- Building table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS Building (
        id SERIAL PRIMARY KEY,
        building_id VARCHAR(50) NOT NULL,
        name VARCHAR(255),
        building_type VARCHAR(50) NOT NULL,
        territory_id VARCHAR(50),
        durability INTEGER NOT NULL DEFAULT 10,
        status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
        upkeep_ore INTEGER DEFAULT 0,
        upkeep_lumber INTEGER DEFAULT 0,
        upkeep_coal INTEGER DEFAULT 0,
        upkeep_rations INTEGER DEFAULT 0,
        upkeep_cloth INTEGER DEFAULT 0,
        upkeep_platinum INTEGER DEFAULT 0,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(building_id, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE Building ADD COLUMN IF NOT EXISTS building_id VARCHAR(50);")
    await conn.execute("ALTER TABLE Building ADD COLUMN IF NOT EXISTS name VARCHAR(255);")
    await conn.execute("ALTER TABLE Building ADD COLUMN IF NOT EXISTS building_type VARCHAR(50);")
    await conn.execute("ALTER TABLE Building ADD COLUMN IF NOT EXISTS territory_id VARCHAR(50);")
    await conn.execute("ALTER TABLE Building ADD COLUMN IF NOT EXISTS durability INTEGER DEFAULT 10;")
    await conn.execute("ALTER TABLE Building ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'ACTIVE';")
    await conn.execute("ALTER TABLE Building ADD COLUMN IF NOT EXISTS upkeep_ore INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Building ADD COLUMN IF NOT EXISTS upkeep_lumber INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Building ADD COLUMN IF NOT EXISTS upkeep_coal INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Building ADD COLUMN IF NOT EXISTS upkeep_rations INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Building ADD COLUMN IF NOT EXISTS upkeep_cloth INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Building ADD COLUMN IF NOT EXISTS upkeep_platinum INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Building ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # Create index for buildings by territory
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_building_territory
        ON Building(territory_id, guild_id);
    """)

    # --- PlayerResources table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS PlayerResources (
        id SERIAL PRIMARY KEY,
        character_id INTEGER NOT NULL REFERENCES Character(id) ON DELETE CASCADE,
        ore INTEGER DEFAULT 0,
        lumber INTEGER DEFAULT 0,
        coal INTEGER DEFAULT 0,
        rations INTEGER DEFAULT 0,
        cloth INTEGER DEFAULT 0,
        platinum INTEGER DEFAULT 0,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(character_id, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE PlayerResources ADD COLUMN IF NOT EXISTS character_id INTEGER;")
    await conn.execute("ALTER TABLE PlayerResources ADD COLUMN IF NOT EXISTS ore INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE PlayerResources ADD COLUMN IF NOT EXISTS lumber INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE PlayerResources ADD COLUMN IF NOT EXISTS coal INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE PlayerResources ADD COLUMN IF NOT EXISTS rations INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE PlayerResources ADD COLUMN IF NOT EXISTS cloth INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE PlayerResources ADD COLUMN IF NOT EXISTS platinum INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE PlayerResources ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # Drop old ResourceTransfer table if it exists
    await conn.execute('DROP TABLE IF EXISTS ResourceTransfer CASCADE;')

    # --- TerritoryAdjacency table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS TerritoryAdjacency (
        id SERIAL PRIMARY KEY,
        territory_a_id VARCHAR(50) NOT NULL,
        territory_b_id VARCHAR(50) NOT NULL,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(territory_a_id, territory_b_id, guild_id),
        CHECK (territory_a_id < territory_b_id)
    );
    """)

    await conn.execute("ALTER TABLE TerritoryAdjacency ADD COLUMN IF NOT EXISTS territory_a_id VARCHAR(50);")
    await conn.execute("ALTER TABLE TerritoryAdjacency ADD COLUMN IF NOT EXISTS territory_b_id VARCHAR(50);")
    await conn.execute("ALTER TABLE TerritoryAdjacency ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # Migration: Change territory_a_id and territory_b_id from INTEGER to VARCHAR(50) for existing databases
    await conn.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'territoryadjacency' AND column_name = 'territory_a_id' AND data_type = 'integer'
            ) THEN
                -- Drop the CHECK constraint first
                ALTER TABLE TerritoryAdjacency DROP CONSTRAINT IF EXISTS territoryadjacency_check;
                ALTER TABLE TerritoryAdjacency DROP CONSTRAINT IF EXISTS territoryadjacency_territory_a_id_check;
                -- Alter column types
                ALTER TABLE TerritoryAdjacency ALTER COLUMN territory_a_id TYPE VARCHAR(50) USING territory_a_id::VARCHAR;
                ALTER TABLE TerritoryAdjacency ALTER COLUMN territory_b_id TYPE VARCHAR(50) USING territory_b_id::VARCHAR;
                -- Recreate the CHECK constraint for string comparison
                ALTER TABLE TerritoryAdjacency ADD CONSTRAINT territoryadjacency_check CHECK (territory_a_id < territory_b_id);
            END IF;
        END $$;
    """)

    # --- WargameConfig table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS WargameConfig (
        guild_id BIGINT PRIMARY KEY REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        current_turn INTEGER DEFAULT 0,
        turn_resolution_enabled BOOLEAN DEFAULT FALSE,
        last_turn_time TIMESTAMP,
        max_movement_stat INTEGER DEFAULT 4,
        gm_reports_channel_id BIGINT
    );
    """)

    await conn.execute("ALTER TABLE WargameConfig ADD COLUMN IF NOT EXISTS current_turn INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE WargameConfig ADD COLUMN IF NOT EXISTS turn_resolution_enabled BOOLEAN DEFAULT FALSE;")
    await conn.execute("ALTER TABLE WargameConfig ADD COLUMN IF NOT EXISTS last_turn_time TIMESTAMP;")
    await conn.execute("ALTER TABLE WargameConfig ADD COLUMN IF NOT EXISTS max_movement_stat INTEGER DEFAULT 4;")
    await conn.execute("ALTER TABLE WargameConfig ADD COLUMN IF NOT EXISTS gm_reports_channel_id BIGINT;")

    # --- Drop old "Order" table if it exists ---
    await conn.execute('DROP TABLE IF EXISTS "Order" CASCADE;')

    # --- WargameOrder table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS WargameOrder (
        id SERIAL PRIMARY KEY,
        order_id VARCHAR(50) NOT NULL,
        order_type VARCHAR(50) NOT NULL,
        unit_ids INTEGER[] NOT NULL DEFAULT '{}',
        character_id INTEGER NOT NULL REFERENCES Character(id) ON DELETE CASCADE,
        turn_number INTEGER NOT NULL,
        phase VARCHAR(50) NOT NULL,
        priority INTEGER DEFAULT 0,
        status VARCHAR(50) DEFAULT 'PENDING',
        order_data JSONB NOT NULL,
        result_data JSONB,
        submitted_at TIMESTAMP DEFAULT NOW(),
        updated_at TIMESTAMP,
        updated_turn INTEGER,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(order_id, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS order_id VARCHAR(50);")
    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS order_type VARCHAR(50);")
    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS unit_ids INTEGER[] DEFAULT '{}';")
    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS character_id INTEGER;")
    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS turn_number INTEGER;")
    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS phase VARCHAR(50);")
    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS priority INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'PENDING';")
    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS order_data JSONB;")
    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS result_data JSONB;")
    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP DEFAULT NOW();")
    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;")
    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS updated_turn INTEGER;")
    await conn.execute("ALTER TABLE WargameOrder ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # Create indexes for WargameOrder table
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_order_turn_phase_status_submitted
        ON WargameOrder(turn_number, phase, status, priority, submitted_at, guild_id);
    """)
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_order_character
        ON WargameOrder(character_id, guild_id);
    """)

    # --- FactionJoinRequest table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS FactionJoinRequest (
        id SERIAL PRIMARY KEY,
        character_id INTEGER NOT NULL REFERENCES Character(id) ON DELETE CASCADE,
        faction_id INTEGER NOT NULL REFERENCES Faction(id) ON DELETE CASCADE,
        submitted_by VARCHAR(20) NOT NULL,
        submitted_at TIMESTAMP DEFAULT NOW(),
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(character_id, faction_id, submitted_by, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE FactionJoinRequest ADD COLUMN IF NOT EXISTS character_id INTEGER;")
    await conn.execute("ALTER TABLE FactionJoinRequest ADD COLUMN IF NOT EXISTS faction_id INTEGER;")
    await conn.execute("ALTER TABLE FactionJoinRequest ADD COLUMN IF NOT EXISTS submitted_by VARCHAR(20);")
    await conn.execute("ALTER TABLE FactionJoinRequest ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP DEFAULT NOW();")
    await conn.execute("ALTER TABLE FactionJoinRequest ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # Create index for FactionJoinRequest table
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_faction_join_request_lookup
        ON FactionJoinRequest(character_id, faction_id, guild_id);
    """)

    # --- TurnLog table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS TurnLog (
        id SERIAL PRIMARY KEY,
        turn_number INTEGER NOT NULL,
        phase VARCHAR(50) NOT NULL,
        event_type VARCHAR(50) NOT NULL,
        entity_type VARCHAR(50),
        entity_id INTEGER,
        event_data JSONB NOT NULL,
        timestamp TIMESTAMP DEFAULT NOW(),
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE
    );
    """)

    await conn.execute("ALTER TABLE TurnLog ADD COLUMN IF NOT EXISTS turn_number INTEGER;")
    await conn.execute("ALTER TABLE TurnLog ADD COLUMN IF NOT EXISTS phase VARCHAR(50);")
    await conn.execute("ALTER TABLE TurnLog ADD COLUMN IF NOT EXISTS event_type VARCHAR(50);")
    await conn.execute("ALTER TABLE TurnLog ADD COLUMN IF NOT EXISTS entity_type VARCHAR(50);")
    await conn.execute("ALTER TABLE TurnLog ADD COLUMN IF NOT EXISTS entity_id INTEGER;")
    await conn.execute("ALTER TABLE TurnLog ADD COLUMN IF NOT EXISTS event_data JSONB;")
    await conn.execute("ALTER TABLE TurnLog ADD COLUMN IF NOT EXISTS timestamp TIMESTAMP DEFAULT NOW();")
    await conn.execute("ALTER TABLE TurnLog ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # Create indexes for TurnLog table
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_turn_log_turn
        ON TurnLog(turn_number, guild_id);
    """)
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_turn_log_entity
        ON TurnLog(entity_type, entity_id, guild_id);
    """)

    # --- Alliance table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS Alliance (
        id SERIAL PRIMARY KEY,
        faction_a_id INTEGER NOT NULL REFERENCES Faction(id) ON DELETE CASCADE,
        faction_b_id INTEGER NOT NULL REFERENCES Faction(id) ON DELETE CASCADE,
        status VARCHAR(20) NOT NULL DEFAULT 'PENDING_FACTION_A',
        initiated_by_faction_id INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        activated_at TIMESTAMP,
        activated_turn INTEGER,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(faction_a_id, faction_b_id, guild_id),
        CHECK (faction_a_id < faction_b_id)
    );
    """)

    await conn.execute("ALTER TABLE Alliance ADD COLUMN IF NOT EXISTS faction_a_id INTEGER;")
    await conn.execute("ALTER TABLE Alliance ADD COLUMN IF NOT EXISTS faction_b_id INTEGER;")
    await conn.execute("ALTER TABLE Alliance ADD COLUMN IF NOT EXISTS status VARCHAR(20) DEFAULT 'PENDING_FACTION_A';")
    await conn.execute("ALTER TABLE Alliance ADD COLUMN IF NOT EXISTS initiated_by_faction_id INTEGER;")
    await conn.execute("ALTER TABLE Alliance ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();")
    await conn.execute("ALTER TABLE Alliance ADD COLUMN IF NOT EXISTS activated_at TIMESTAMP;")
    await conn.execute("ALTER TABLE Alliance ADD COLUMN IF NOT EXISTS activated_turn INTEGER;")
    await conn.execute("ALTER TABLE Alliance ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # Create index for Alliance table
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_alliance_lookup
        ON Alliance(faction_a_id, faction_b_id, guild_id);
    """)
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_alliance_faction
        ON Alliance(faction_a_id, guild_id);
    """)
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_alliance_faction_b
        ON Alliance(faction_b_id, guild_id);
    """)

    # --- War table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS War (
        id SERIAL PRIMARY KEY,
        war_id VARCHAR(255) NOT NULL,
        objective TEXT NOT NULL,
        declared_turn INTEGER NOT NULL,
        created_at TIMESTAMP DEFAULT NOW(),
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(war_id, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE War ADD COLUMN IF NOT EXISTS war_id VARCHAR(255);")
    await conn.execute("ALTER TABLE War ADD COLUMN IF NOT EXISTS objective TEXT;")
    await conn.execute("ALTER TABLE War ADD COLUMN IF NOT EXISTS declared_turn INTEGER;")
    await conn.execute("ALTER TABLE War ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();")
    await conn.execute("ALTER TABLE War ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # Create index for War table
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_war_objective
        ON War(LOWER(objective), guild_id);
    """)

    # --- WarParticipant table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS WarParticipant (
        id SERIAL PRIMARY KEY,
        war_id INTEGER NOT NULL REFERENCES War(id) ON DELETE CASCADE,
        faction_id INTEGER NOT NULL REFERENCES Faction(id) ON DELETE CASCADE,
        side VARCHAR(10) NOT NULL CHECK (side IN ('SIDE_A', 'SIDE_B')),
        joined_turn INTEGER NOT NULL,
        is_original_declarer BOOLEAN NOT NULL DEFAULT FALSE,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(war_id, faction_id, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE WarParticipant ADD COLUMN IF NOT EXISTS war_id INTEGER;")
    await conn.execute("ALTER TABLE WarParticipant ADD COLUMN IF NOT EXISTS faction_id INTEGER;")
    await conn.execute("ALTER TABLE WarParticipant ADD COLUMN IF NOT EXISTS side VARCHAR(10);")
    await conn.execute("ALTER TABLE WarParticipant ADD COLUMN IF NOT EXISTS joined_turn INTEGER;")
    await conn.execute("ALTER TABLE WarParticipant ADD COLUMN IF NOT EXISTS is_original_declarer BOOLEAN DEFAULT FALSE;")
    await conn.execute("ALTER TABLE WarParticipant ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # Create indexes for WarParticipant table
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_war_participant_war
        ON WarParticipant(war_id, guild_id);
    """)
    await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_war_participant_faction
        ON WarParticipant(faction_id, guild_id);
    """)

    # --- ScheduledTurn table (for future auto-scheduling) ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS ScheduledTurn (
        id SERIAL PRIMARY KEY,
        scheduled_time TIMESTAMP NOT NULL,
        status VARCHAR(50) DEFAULT 'SCHEDULED',
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(scheduled_time, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE ScheduledTurn ADD COLUMN IF NOT EXISTS scheduled_time TIMESTAMP;")
    await conn.execute("ALTER TABLE ScheduledTurn ADD COLUMN IF NOT EXISTS status VARCHAR(50) DEFAULT 'SCHEDULED';")
    await conn.execute("ALTER TABLE ScheduledTurn ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # --- Add foreign key constraints for faction ownership ---
    # FK for Territory.controller_faction_id -> Faction.id (ON DELETE SET NULL)
    await conn.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'territory_controller_faction_id_fkey'
        ) THEN
            ALTER TABLE Territory
            ADD CONSTRAINT territory_controller_faction_id_fkey
            FOREIGN KEY (controller_faction_id) REFERENCES Faction(id) ON DELETE SET NULL;
        END IF;
    END$$;
    """)

    # FK for Unit.owner_faction_id -> Faction.id (ON DELETE CASCADE)
    await conn.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'unit_owner_faction_id_fkey'
        ) THEN
            ALTER TABLE Unit
            ADD CONSTRAINT unit_owner_faction_id_fkey
            FOREIGN KEY (owner_faction_id) REFERENCES Faction(id) ON DELETE CASCADE;
        END IF;
    END$$;
    """)

    # FK for Character.represented_faction_id -> Faction.id (ON DELETE SET NULL)
    await conn.execute("""
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = 'character_represented_faction_id_fkey'
        ) THEN
            ALTER TABLE Character
            ADD CONSTRAINT character_represented_faction_id_fkey
            FOREIGN KEY (represented_faction_id) REFERENCES Faction(id) ON DELETE SET NULL;
        END IF;
    END$$;
    """)

    # --- Migrate existing faction leaders to have all permissions ---
    VALID_PERMISSION_TYPES = ["COMMAND", "FINANCIAL", "MEMBERSHIP", "CONSTRUCTION"]
    factions = await conn.fetch("""
        SELECT id, leader_character_id, guild_id
        FROM Faction
        WHERE leader_character_id IS NOT NULL
    """)
    for faction in factions:
        for perm_type in VALID_PERMISSION_TYPES:
            await conn.execute("""
                INSERT INTO FactionPermission (faction_id, character_id, permission_type, guild_id)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT DO NOTHING;
            """, faction['id'], faction['leader_character_id'], perm_type, faction['guild_id'])
    if factions:
        logger.info(f"Migrated permissions for {len(factions)} faction leaders")

    # --- HERBALISM TABLES (shared across all guilds, no guild_id) ---

    # --- Ingredient table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS Ingredient (
        id SERIAL PRIMARY KEY,
        item_number VARCHAR(20) NOT NULL UNIQUE,
        name TEXT NOT NULL,
        macro TEXT,
        rarity TEXT,
        primary_chakra VARCHAR(20),
        primary_chakra_strength INTEGER,
        secondary_chakra VARCHAR(20),
        secondary_chakra_strength INTEGER,
        properties TEXT,
        flavor_text TEXT,
        rules_text TEXT,
        skip_export BOOLEAN DEFAULT FALSE
    );
    """)

    await conn.execute("ALTER TABLE Ingredient ADD COLUMN IF NOT EXISTS item_number VARCHAR(20);")
    await conn.execute("ALTER TABLE Ingredient ADD COLUMN IF NOT EXISTS name TEXT;")
    await conn.execute("ALTER TABLE Ingredient ADD COLUMN IF NOT EXISTS macro TEXT;")
    await conn.execute("ALTER TABLE Ingredient ADD COLUMN IF NOT EXISTS rarity TEXT;")
    await conn.execute("ALTER TABLE Ingredient ADD COLUMN IF NOT EXISTS primary_chakra VARCHAR(20);")
    await conn.execute("ALTER TABLE Ingredient ADD COLUMN IF NOT EXISTS primary_chakra_strength INTEGER;")
    await conn.execute("ALTER TABLE Ingredient ADD COLUMN IF NOT EXISTS secondary_chakra VARCHAR(20);")
    await conn.execute("ALTER TABLE Ingredient ADD COLUMN IF NOT EXISTS secondary_chakra_strength INTEGER;")
    await conn.execute("ALTER TABLE Ingredient ADD COLUMN IF NOT EXISTS properties TEXT;")
    await conn.execute("ALTER TABLE Ingredient ADD COLUMN IF NOT EXISTS flavor_text TEXT;")
    await conn.execute("ALTER TABLE Ingredient ADD COLUMN IF NOT EXISTS rules_text TEXT;")
    await conn.execute("ALTER TABLE Ingredient ADD COLUMN IF NOT EXISTS skip_export BOOLEAN DEFAULT FALSE;")

    # --- Product table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS Product (
        id SERIAL PRIMARY KEY,
        item_number VARCHAR(20) NOT NULL UNIQUE,
        name TEXT,
        macro TEXT,
        product_type TEXT,
        flavor_text TEXT,
        rules_text TEXT,
        skip_export BOOLEAN DEFAULT FALSE
    );
    """)

    await conn.execute("ALTER TABLE Product ADD COLUMN IF NOT EXISTS item_number VARCHAR(20);")
    await conn.execute("ALTER TABLE Product ADD COLUMN IF NOT EXISTS name TEXT;")
    await conn.execute("ALTER TABLE Product ADD COLUMN IF NOT EXISTS macro TEXT;")
    await conn.execute("ALTER TABLE Product ADD COLUMN IF NOT EXISTS product_type TEXT;")
    await conn.execute("ALTER TABLE Product ADD COLUMN IF NOT EXISTS flavor_text TEXT;")
    await conn.execute("ALTER TABLE Product ADD COLUMN IF NOT EXISTS rules_text TEXT;")
    await conn.execute("ALTER TABLE Product ADD COLUMN IF NOT EXISTS skip_export BOOLEAN DEFAULT FALSE;")

    # --- SubsetRecipe table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS SubsetRecipe (
        id SERIAL PRIMARY KEY,
        product_item_number VARCHAR(20) NOT NULL,
        product_type TEXT NOT NULL,
        quantity_produced INTEGER DEFAULT 1,
        ingredients TEXT[] NOT NULL
    );
    """)

    await conn.execute("ALTER TABLE SubsetRecipe ADD COLUMN IF NOT EXISTS product_item_number VARCHAR(20);")
    await conn.execute("ALTER TABLE SubsetRecipe ADD COLUMN IF NOT EXISTS product_type TEXT;")
    await conn.execute("ALTER TABLE SubsetRecipe ADD COLUMN IF NOT EXISTS quantity_produced INTEGER DEFAULT 1;")
    await conn.execute("ALTER TABLE SubsetRecipe ADD COLUMN IF NOT EXISTS ingredients TEXT[];")

    # --- ConstraintRecipe table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS ConstraintRecipe (
        id SERIAL PRIMARY KEY,
        product_item_number VARCHAR(20) NOT NULL,
        product_type TEXT NOT NULL,
        quantity_produced INTEGER DEFAULT 1,
        ingredients TEXT[],
        primary_chakra VARCHAR(20),
        primary_is_boon VARCHAR(10),
        secondary_chakra VARCHAR(20),
        secondary_is_boon VARCHAR(10),
        tier INTEGER,
        created_at TIMESTAMP DEFAULT NOW()
    );
    """)

    await conn.execute("ALTER TABLE ConstraintRecipe ADD COLUMN IF NOT EXISTS product_item_number VARCHAR(20);")
    await conn.execute("ALTER TABLE ConstraintRecipe ADD COLUMN IF NOT EXISTS product_type TEXT;")
    await conn.execute("ALTER TABLE ConstraintRecipe ADD COLUMN IF NOT EXISTS quantity_produced INTEGER DEFAULT 1;")
    await conn.execute("ALTER TABLE ConstraintRecipe ADD COLUMN IF NOT EXISTS ingredients TEXT[];")
    await conn.execute("ALTER TABLE ConstraintRecipe ADD COLUMN IF NOT EXISTS primary_chakra VARCHAR(20);")
    await conn.execute("ALTER TABLE ConstraintRecipe ADD COLUMN IF NOT EXISTS primary_is_boon VARCHAR(10);")
    await conn.execute("ALTER TABLE ConstraintRecipe ADD COLUMN IF NOT EXISTS secondary_chakra VARCHAR(20);")
    await conn.execute("ALTER TABLE ConstraintRecipe ADD COLUMN IF NOT EXISTS secondary_is_boon VARCHAR(10);")
    await conn.execute("ALTER TABLE ConstraintRecipe ADD COLUMN IF NOT EXISTS tier INTEGER;")
    await conn.execute("ALTER TABLE ConstraintRecipe ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();")

    # --- FailedBlend table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS FailedBlend (
        id SERIAL PRIMARY KEY,
        product_item_number VARCHAR(20) NOT NULL,
        product_type TEXT NOT NULL UNIQUE
    );
    """)

    await conn.execute("ALTER TABLE FailedBlend ADD COLUMN IF NOT EXISTS product_item_number VARCHAR(20);")
    await conn.execute("ALTER TABLE FailedBlend ADD COLUMN IF NOT EXISTS product_type TEXT;")

    # --- Evidence table (global, no guild_id) ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS Evidence (
        id SERIAL PRIMARY KEY,
        analysis_number VARCHAR(50) NOT NULL UNIQUE,
        hint TEXT NOT NULL,
        gm_notes TEXT NOT NULL
    );
    """)

    await conn.execute("ALTER TABLE Evidence ADD COLUMN IF NOT EXISTS analysis_number VARCHAR(50);")
    await conn.execute("ALTER TABLE Evidence ADD COLUMN IF NOT EXISTS hint TEXT;")
    await conn.execute("ALTER TABLE Evidence ADD COLUMN IF NOT EXISTS gm_notes TEXT;")

    logger.info("Schema verified and updated successfully.")
    await conn.close()

    
# Run
if __name__ == "__main__":
    asyncio.run(ensure_tables())
    asyncio.run(inspect_database())

