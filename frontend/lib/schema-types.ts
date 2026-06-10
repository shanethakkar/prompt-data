// Mirrors the backend /schema payload (pipeline/schema.py TableInfo/ColumnInfo).
export interface SchemaColumn {
  name: string;
  type: string;
  note: string | null;
  primary_key: boolean;
}

export interface SchemaTable {
  name: string;
  description: string | null;
  row_count: number;
  columns: SchemaColumn[];
  foreign_keys: string[];
}

export interface SchemaResponse {
  dataset: string;
  tables: SchemaTable[];
}

export interface UploadResponse {
  session: string;
  label: string;
  filename: string | null;
  tables: SchemaTable[];
}

// The active dataset: the built-in Olist demo, or an uploaded bring-your-own file.
export type Dataset =
  | { kind: "olist" }
  | { kind: "custom"; session: string; filename: string | null; tables: SchemaTable[] };
