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
        territory_id INTEGER NOT NULL,
        name VARCHAR(255),
        terrain_type VARCHAR(50) NOT NULL,
        ore_production INTEGER DEFAULT 0,
        lumber_production INTEGER DEFAULT 0,
        coal_production INTEGER DEFAULT 0,
        rations_production INTEGER DEFAULT 0,
        cloth_production INTEGER DEFAULT 0,
        controller_faction_id INTEGER,
        original_nation VARCHAR(50),
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(territory_id, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS territory_id INTEGER;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS name VARCHAR(255);")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS terrain_type VARCHAR(50);")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS ore_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS lumber_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS coal_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS rations_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS cloth_production INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS controller_faction_id INTEGER;")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS original_nation VARCHAR(50);")
    await conn.execute("ALTER TABLE Territory ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

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
    await conn.execute("ALTER TABLE Faction ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # --- FactionMember table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS FactionMember (
        id SERIAL PRIMARY KEY,
        faction_id INTEGER NOT NULL REFERENCES Faction(id) ON DELETE CASCADE,
        character_id INTEGER NOT NULL REFERENCES Character(id) ON DELETE CASCADE,
        joined_turn INTEGER NOT NULL,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(character_id, guild_id)
    );
    """)

    await conn.execute("ALTER TABLE FactionMember ADD COLUMN IF NOT EXISTS faction_id INTEGER;")
    await conn.execute("ALTER TABLE FactionMember ADD COLUMN IF NOT EXISTS character_id INTEGER;")
    await conn.execute("ALTER TABLE FactionMember ADD COLUMN IF NOT EXISTS joined_turn INTEGER;")
    await conn.execute("ALTER TABLE FactionMember ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

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
        current_territory_id INTEGER,
        is_naval BOOLEAN DEFAULT FALSE,
        upkeep_ore INTEGER DEFAULT 0,
        upkeep_lumber INTEGER DEFAULT 0,
        upkeep_coal INTEGER DEFAULT 0,
        upkeep_rations INTEGER DEFAULT 0,
        upkeep_cloth INTEGER DEFAULT 0,
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
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS current_territory_id INTEGER;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS is_naval BOOLEAN DEFAULT FALSE;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS upkeep_ore INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS upkeep_lumber INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS upkeep_coal INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS upkeep_rations INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS upkeep_cloth INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS keywords TEXT[];")
    await conn.execute("ALTER TABLE Unit ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

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
        upkeep_ore INTEGER DEFAULT 0,
        upkeep_lumber INTEGER DEFAULT 0,
        upkeep_coal INTEGER DEFAULT 0,
        upkeep_rations INTEGER DEFAULT 0,
        upkeep_cloth INTEGER DEFAULT 0,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(type_id, nation, guild_id)
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
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS upkeep_ore INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS upkeep_lumber INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS upkeep_coal INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS upkeep_rations INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS upkeep_cloth INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE UnitType ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

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
    await conn.execute("ALTER TABLE PlayerResources ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # --- ResourceTransfer table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS ResourceTransfer (
        id SERIAL PRIMARY KEY,
        from_character_id INTEGER REFERENCES Character(id) ON DELETE SET NULL,
        to_character_id INTEGER REFERENCES Character(id) ON DELETE SET NULL,
        ore INTEGER DEFAULT 0,
        lumber INTEGER DEFAULT 0,
        coal INTEGER DEFAULT 0,
        rations INTEGER DEFAULT 0,
        cloth INTEGER DEFAULT 0,
        reason VARCHAR(255),
        transfer_time TIMESTAMP NOT NULL DEFAULT NOW(),
        turn_number INTEGER,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE
    );
    """)

    await conn.execute("ALTER TABLE ResourceTransfer ADD COLUMN IF NOT EXISTS from_character_id INTEGER;")
    await conn.execute("ALTER TABLE ResourceTransfer ADD COLUMN IF NOT EXISTS to_character_id INTEGER;")
    await conn.execute("ALTER TABLE ResourceTransfer ADD COLUMN IF NOT EXISTS ore INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE ResourceTransfer ADD COLUMN IF NOT EXISTS lumber INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE ResourceTransfer ADD COLUMN IF NOT EXISTS coal INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE ResourceTransfer ADD COLUMN IF NOT EXISTS rations INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE ResourceTransfer ADD COLUMN IF NOT EXISTS cloth INTEGER DEFAULT 0;")
    await conn.execute("ALTER TABLE ResourceTransfer ADD COLUMN IF NOT EXISTS reason VARCHAR(255);")
    await conn.execute("ALTER TABLE ResourceTransfer ADD COLUMN IF NOT EXISTS transfer_time TIMESTAMP DEFAULT NOW();")
    await conn.execute("ALTER TABLE ResourceTransfer ADD COLUMN IF NOT EXISTS turn_number INTEGER;")
    await conn.execute("ALTER TABLE ResourceTransfer ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

    # --- TerritoryAdjacency table ---
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS TerritoryAdjacency (
        id SERIAL PRIMARY KEY,
        territory_a_id INTEGER NOT NULL,
        territory_b_id INTEGER NOT NULL,
        guild_id BIGINT NOT NULL REFERENCES ServerConfig(guild_id) ON DELETE CASCADE,
        UNIQUE(territory_a_id, territory_b_id, guild_id),
        CHECK (territory_a_id < territory_b_id)
    );
    """)

    await conn.execute("ALTER TABLE TerritoryAdjacency ADD COLUMN IF NOT EXISTS territory_a_id INTEGER;")
    await conn.execute("ALTER TABLE TerritoryAdjacency ADD COLUMN IF NOT EXISTS territory_b_id INTEGER;")
    await conn.execute("ALTER TABLE TerritoryAdjacency ADD COLUMN IF NOT EXISTS guild_id BIGINT;")

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

    logger.info("Schema verified and updated successfully.")
    await conn.close()

    
# Run
if __name__ == "__main__":
    asyncio.run(ensure_tables())
    asyncio.run(inspect_database())

