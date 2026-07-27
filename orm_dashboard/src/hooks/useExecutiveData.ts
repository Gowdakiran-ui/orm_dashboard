import { useState } from "react";
import { promoteExecutiveCandidates, promoteCompetitorCandidates } from "@/lib/api";

export function useExecutiveData(clientId: string | null, onRefresh: () => void) {
  const [promotingExecutives, setPromotingExecutives] = useState(false);
  const [promotingCompetitors, setPromotingCompetitors] = useState(false);

  async function handlePromoteExecutives() {
    if (!clientId || promotingExecutives) return;
    setPromotingExecutives(true);
    try {
      await promoteExecutiveCandidates(clientId);
      onRefresh();
    } catch (e: any) {
      console.error("Failed to promote executives", e);
    } finally {
      setPromotingExecutives(false);
    }
  }

  async function handlePromoteCompetitors() {
    if (!clientId || promotingCompetitors) return;
    setPromotingCompetitors(true);
    try {
      await promoteCompetitorCandidates(clientId);
      onRefresh();
    } catch (e: any) {
      console.error("Failed to promote competitors", e);
    } finally {
      setPromotingCompetitors(false);
    }
  }

  return {
    promotingExecutives,
    handlePromoteExecutives,
    promotingCompetitors,
    handlePromoteCompetitors
  };
}
