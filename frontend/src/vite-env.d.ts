/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_EVAS_API_BASE?: string;
  readonly VITE_EVAS_BOOTSTRAP_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
