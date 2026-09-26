ALTER TABLE place_submissions
  DROP CONSTRAINT place_submissions_check;

ALTER TABLE place_submissions
  ADD CONSTRAINT place_submissions_intent_place_check CHECK (
    (intent = 'correct' AND place_id IS NOT NULL)
    OR (
      intent = 'create'
      AND (
        (state IN ('pending', 'rejected') AND place_id IS NULL)
        OR (state IN ('published', 'merged') AND place_id IS NOT NULL)
      )
    )
  );
