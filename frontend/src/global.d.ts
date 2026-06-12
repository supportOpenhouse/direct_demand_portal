/**
 * Hand-declared globals for the two lazily-loaded Google scripts:
 * - Google Identity Services (index.html <script src=".../gsi/client">)
 * - Google Maps JS API (injected by useGoogleMaps when VITE_MAPS_API_KEY is set)
 */

interface GsiCredentialResponse {
  credential: string;
  select_by?: string;
}

interface GsiIdApi {
  initialize(config: {
    client_id: string;
    callback: (response: GsiCredentialResponse) => void;
    [key: string]: unknown;
  }): void;
  renderButton(parent: HTMLElement, options: Record<string, unknown>): void;
  prompt?(): void;
}

interface GoogleGlobal {
  accounts?: { id: GsiIdApi };
  /* Google Maps namespace — typed loosely on purpose (no @types/google.maps dep). */
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  maps?: any;
}

interface Window {
  google?: GoogleGlobal;
}
