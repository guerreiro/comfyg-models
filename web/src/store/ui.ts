import { create } from "zustand";

interface UiState {
  bootstrapReady: boolean;
  setBootstrapReady: (ready: boolean) => void;
}

export const useUiStore = create<UiState>((set) => ({
  bootstrapReady: true,
  setBootstrapReady: (ready) => set({ bootstrapReady: ready }),
}));
