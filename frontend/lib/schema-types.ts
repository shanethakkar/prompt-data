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
