import React, { useState } from 'react';
import { KeyRound } from 'lucide-react';
import { Modal } from './ui';

interface ApiKeyDialogProps {
  error?: string | null;
  onSubmit: (key: string) => void;
  onCancel: () => void;
}

// Asked when POST /api/jobs/run answers 401 (server has API_SECRET_KEY set)
export const ApiKeyDialog: React.FC<ApiKeyDialogProps> = ({ error, onSubmit, onCancel }) => {
  const [value, setValue] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (value.trim()) onSubmit(value.trim());
  };

  return (
    <Modal onClose={onCancel} labelledBy="api-key-title" className="modal-sm" closeButton={false}>
      <form onSubmit={handleSubmit} className="api-key-form">
        <h2 id="api-key-title" className="dialog-title">
          <KeyRound size={18} color="var(--accent-cyan)" /> API key required
        </h2>
        <p className="text-muted text-sm">
          This server requires <code>API_SECRET_KEY</code> to run the pipeline. The key is stored in this browser only.
        </p>
        <label htmlFor="api-key-input" className="field-label">API key</label>
        <input
          id="api-key-input"
          type="password"
          autoComplete="off"
          autoFocus
          className="text-input"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-invalid={!!error}
          aria-describedby={error ? 'api-key-error' : undefined}
        />
        {error && <p id="api-key-error" className="field-error">{error}</p>}
        <div className="dialog-actions">
          <button type="button" className="btn btn-secondary btn-md" onClick={onCancel}>Cancel</button>
          <button type="submit" className="btn btn-primary btn-md" disabled={!value.trim()}>Run pipeline</button>
        </div>
      </form>
    </Modal>
  );
};
