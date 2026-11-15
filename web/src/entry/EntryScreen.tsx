import type { FormEvent } from "react";
import { useState } from "react";
import { createTable } from "../api/createTable";
import type { EntryField } from "../api/errors";
import { joinTable } from "../api/joinTable";
import { Button } from "../ui/Button";
import { ProductLogo } from "../ui/ProductLogo";
import { storeSession } from "./credentialStorage";
import styles from "./EntryScreen.module.css";

export interface EntryScreenProps {
  onEnter: (tableId: string, credential: string) => void;
}

interface FormErrors {
  [field: string]: string | undefined;
}

/** The branded single entry screen (W17): Create, and Join with a seat
 * number from 1 to 9 (C6.2 plan §2.5). */
export function EntryScreen({ onEnter }: EntryScreenProps) {
  const [createName, setCreateName] = useState("");
  const [createBusy, setCreateBusy] = useState(false);
  const [createErrors, setCreateErrors] = useState<FormErrors>({});

  const [joinCode, setJoinCode] = useState("");
  const [joinName, setJoinName] = useState("");
  const [joinSeat, setJoinSeat] = useState(1);
  const [joinBusy, setJoinBusy] = useState(false);
  const [joinErrors, setJoinErrors] = useState<FormErrors>({});

  function setFieldError(setErrors: (e: FormErrors) => void, field: EntryField, message: string) {
    setErrors({ [field]: message });
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setCreateBusy(true);
    setCreateErrors({});
    try {
      const result = await createTable(createName);
      if (result.ok) {
        storeSession(result.data.table_id, result.data.credential);
        onEnter(result.data.table_id, result.data.credential);
      } else {
        setFieldError(setCreateErrors, result.error.field, result.error.message);
      }
    } finally {
      setCreateBusy(false);
    }
  }

  async function handleJoin(event: FormEvent) {
    event.preventDefault();
    setJoinBusy(true);
    setJoinErrors({});
    try {
      const result = await joinTable(joinCode, joinName, joinSeat);
      if (result.ok) {
        storeSession(result.data.table_id, result.data.credential);
        onEnter(result.data.table_id, result.data.credential);
      } else {
        setFieldError(setJoinErrors, result.error.field, result.error.message);
      }
    } finally {
      setJoinBusy(false);
    }
  }

  return (
    <div className={styles.screen}>
      <ProductLogo variant="wide" />
      <div className={styles.forms}>
        <form className={styles.form} onSubmit={handleCreate}>
          <h2>Create a table</h2>
          <label htmlFor="create-name">Your name</label>
          <input
            id="create-name"
            value={createName}
            onChange={(e) => setCreateName(e.target.value)}
            required
          />
          {createErrors.display_name && <p className={styles.error}>{createErrors.display_name}</p>}
          {createErrors.form && <p className={styles.error}>{createErrors.form}</p>}
          <Button type="submit" variant="primary" disabled={createBusy}>
            Create
          </Button>
        </form>

        <form className={styles.form} onSubmit={handleJoin}>
          <h2>Join with a code</h2>
          <label htmlFor="join-code">Table code</label>
          <input
            id="join-code"
            value={joinCode}
            onChange={(e) => setJoinCode(e.target.value)}
            required
          />
          {joinErrors.code && <p className={styles.error}>{joinErrors.code}</p>}
          <label htmlFor="join-name">Your name</label>
          <input
            id="join-name"
            value={joinName}
            onChange={(e) => setJoinName(e.target.value)}
            required
          />
          {joinErrors.display_name && <p className={styles.error}>{joinErrors.display_name}</p>}
          <label htmlFor="join-seat">Seat (1-9)</label>
          <input
            id="join-seat"
            type="number"
            min={1}
            max={9}
            value={joinSeat}
            onChange={(e) => setJoinSeat(Number(e.target.value))}
            required
          />
          {joinErrors.seat && <p className={styles.error}>{joinErrors.seat}</p>}
          {joinErrors.form && <p className={styles.error}>{joinErrors.form}</p>}
          <Button type="submit" variant="primary" disabled={joinBusy}>
            Join
          </Button>
        </form>
      </div>
    </div>
  );
}
