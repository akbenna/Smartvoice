-- VitaScribe - praktijkregister
--
-- Wordt bij het opstarten van de server uitgevoerd en is daarom idempotent:
-- elke opdracht mag vaker draaien zonder iets te veranderen. Een wijziging
-- aan een bestaande tabel komt hieronder als losse ALTER ... IF NOT EXISTS,
-- nooit door een CREATE aan te passen.

CREATE TABLE IF NOT EXISTS vs_praktijken (
    id                       BIGSERIAL PRIMARY KEY,
    naam                     TEXT NOT NULL,
    plaats                   TEXT NOT NULL DEFAULT '',
    -- Het nummer in de Bricks-URL (https://groep06.brickshuisarts.nl/2876/...).
    -- Leeg = niet praktijkgebonden.
    praktijknummers          TEXT[] NOT NULL DEFAULT '{}',
    agb                      TEXT NOT NULL DEFAULT '',
    contact_naam             TEXT NOT NULL DEFAULT '',
    contact_email            TEXT NOT NULL DEFAULT '',
    telefoon                 TEXT NOT NULL DEFAULT '',
    fte                      NUMERIC(5, 2),
    werkplekken              INTEGER,
    licentietype             TEXT NOT NULL DEFAULT 'kandidaat'
        CHECK (licentietype IN ('kandidaat', 'pilot', 'betaald', 'intern')),
    status                   TEXT NOT NULL DEFAULT 'aangemeld'
        CHECK (status IN ('aangemeld', 'actief', 'uitgehaald', 'afgewezen')),
    -- Leeg = onbeperkt geldig; alleen bedoeld voor de eigen praktijk.
    geldig_tot               DATE,
    serienummer              TEXT NOT NULL DEFAULT '',
    -- Aan: geen brieven of spraak op de sleutels van de server, alleen op die
    -- van de praktijk zelf.
    eigen_sleutels_verplicht BOOLEAN NOT NULL DEFAULT FALSE,
    notities                 TEXT NOT NULL DEFAULT '',
    opmerking_aanmelding     TEXT NOT NULL DEFAULT '',
    aangemeld_op             TIMESTAMPTZ NOT NULL DEFAULT now(),
    bijgewerkt_op            TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS vs_gebruikers (
    id                     BIGSERIAL PRIMARY KEY,
    praktijk_id            BIGINT NOT NULL REFERENCES vs_praktijken(id) ON DELETE CASCADE,
    naam                   TEXT NOT NULL,
    email                  TEXT NOT NULL DEFAULT '',
    rol                    TEXT NOT NULL DEFAULT 'gebruiker'
        CHECK (rol IN ('gebruiker', 'praktijkbeheerder')),
    -- sha256 van de sleutel. De sleutel zelf wordt één keer getoond en nergens bewaard.
    sleutel_hash           TEXT NOT NULL UNIQUE,
    sleutel_hint           TEXT NOT NULL,
    actief                 BOOLEAN NOT NULL DEFAULT TRUE,
    aangemaakt_op          TIMESTAMPTZ NOT NULL DEFAULT now(),
    laatst_gezien          TIMESTAMPTZ,
    laatst_praktijknummer  TEXT
);
CREATE INDEX IF NOT EXISTS vs_gebruikers_praktijk ON vs_gebruikers (praktijk_id);

-- Eigen sleutels van een praktijk bij een AI-dienst, versleuteld (zie kluis.py).
-- 'brieven': Anthropic of OpenAI, alleen voor gepseudonimiseerde brieven.
-- 'spraak':  Deepgram.
CREATE TABLE IF NOT EXISTS vs_praktijk_sleutels (
    praktijk_id     BIGINT NOT NULL REFERENCES vs_praktijken(id) ON DELETE CASCADE,
    dienst          TEXT NOT NULL CHECK (dienst IN ('brieven', 'spraak')),
    aanbieder       TEXT NOT NULL,
    versleuteld     TEXT NOT NULL,
    hint            TEXT NOT NULL,
    ingesteld_door  BIGINT REFERENCES vs_gebruikers(id) ON DELETE SET NULL,
    ingesteld_op    TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (praktijk_id, dienst),
    CHECK ((dienst = 'brieven' AND aanbieder IN ('anthropic', 'openai'))
        OR (dienst = 'spraak' AND aanbieder = 'deepgram'))
);

CREATE TABLE IF NOT EXISTS vs_instellingen (
    sleutel TEXT PRIMARY KEY,
    waarde  TEXT NOT NULL
);

-- Wat er in het beheer gebeurde: welke handeling, bij welke praktijk, wanneer.
-- Nooit een sleutel, ook niet versleuteld.
CREATE TABLE IF NOT EXISTS vs_beheerlog (
    id           BIGSERIAL PRIMARY KEY,
    op           TIMESTAMPTZ NOT NULL DEFAULT now(),
    door         TEXT NOT NULL,
    handeling    TEXT NOT NULL,
    praktijk_id  BIGINT,
    details      JSONB NOT NULL DEFAULT '{}'::jsonb
);
CREATE INDEX IF NOT EXISTS vs_beheerlog_op ON vs_beheerlog (op DESC);
