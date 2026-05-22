-- Structured columns added for React client-side data needs.
-- face_url: max-ascension face image URL extracted from extraAssets JSON, avoids
--           shipping the full data blob to the browser just for the avatar image.
-- opened_at: Unix timestamp (seconds) used to sort events newest-first in the UI.

ALTER TABLE public.servants ADD COLUMN IF NOT EXISTS face_url TEXT;
ALTER TABLE public.quests   ADD COLUMN IF NOT EXISTS opened_at BIGINT;
