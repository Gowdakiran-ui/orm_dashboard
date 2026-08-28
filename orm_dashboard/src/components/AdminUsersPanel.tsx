"use client";

import React, { useEffect, useState, useCallback } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { UserPlus, Trash2, ShieldCheck, Loader2, KeyRound, Copy, Check } from "lucide-react";
import {
  fetchClients, fetchAdminUsers, createUser, resetUserPassword, deleteAdminUser,
  AdminUser, CreateUserPayload, PasswordReveal
} from "@/lib/api";
import { TelemetryErrorWidget } from "@/components/TelemetryErrorWidget";

export function AdminUsersPanel() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [clients, setClients] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createEmail, setCreateEmail] = useState("");
  const [createRole, setCreateRole] = useState<"client_user" | "super_admin">("client_user");
  const [createClientIds, setCreateClientIds] = useState<string[]>([]);
  const [createLoading, setCreateLoading] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);

  const [deleteTarget, setDeleteTarget] = useState<AdminUser | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);
  const [resetLoading, setResetLoading] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);

  // One-time password reveal -- shown after create or reset, for either flow.
  const [passwordReveal, setPasswordReveal] = useState<PasswordReveal | null>(null);
  const [copied, setCopied] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [u, c] = await Promise.all([fetchAdminUsers(), fetchClients()]);
      setUsers(u);
      setClients(c || []);
    } catch (e: any) {
      setError(e.message || "Failed to load users");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  function clientName(id: string): string {
    return clients.find((c: any) => c.id === id)?.name || id;
  }

  function toggleCreateClient(id: string) {
    setCreateClientIds((prev) => prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]);
  }

  async function handleCreate() {
    const trimmedEmail = createEmail.trim();
    if (!trimmedEmail) {
      setCreateError("Email is required");
      return;
    }
    // type="email" alone doesn't validate here -- these buttons aren't a
    // native <form> submit, so the browser's built-in check never runs
    // (confirmed live: "example.gmail.com", no @, was accepted as valid).
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(trimmedEmail)) {
      setCreateError("Enter a valid email address (e.g. name@example.com)");
      return;
    }
    setCreateLoading(true);
    setCreateError(null);
    try {
      const payload: CreateUserPayload = {
        email: createEmail.trim(),
        role: createRole,
        client_ids: createRole === "client_user" ? createClientIds : [],
      };
      const created = await createUser(payload);
      setCreateOpen(false);
      setCreateEmail("");
      setCreateRole("client_user");
      setCreateClientIds([]);
      setPasswordReveal(created);
      await load();
    } catch (e: any) {
      setCreateError(e.message || "Failed to create user");
    } finally {
      setCreateLoading(false);
    }
  }

  async function handleResetPassword() {
    if (!resetTarget) return;
    setResetLoading(true);
    setResetError(null);
    try {
      const result = await resetUserPassword(resetTarget.id);
      setResetTarget(null);
      setPasswordReveal(result);
    } catch (e: any) {
      setResetError(e.message || "Failed to reset password");
    } finally {
      setResetLoading(false);
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      await deleteAdminUser(deleteTarget.id);
      setDeleteTarget(null);
      await load();
    } catch (e: any) {
      setDeleteError(e.message || "Failed to delete user");
    } finally {
      setDeleteLoading(false);
    }
  }

  async function handleCopyPassword() {
    if (!passwordReveal) return;
    try {
      await navigator.clipboard.writeText(passwordReveal.password);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API unavailable (non-secure context, permissions, etc.) --
      // the password is still visible in the dialog for manual copy.
    }
  }

  if (loading) {
    return (
      <div className="space-y-4 animate-pulse">
        <div className="h-10 bg-[#1E293B]/20 border border-[#1F2937]/60 rounded-lg w-48" />
        <div className="h-64 bg-[#1E293B]/10 border border-[#1F2937]/60 rounded-lg" />
      </div>
    );
  }

  if (error) {
    return (
      <Card className="bg-[#060B18]/60 border-red-500/20 h-96">
        <TelemetryErrorWidget title="User Management Offline" message={error} />
      </Card>
    );
  }

  return (
    <div className="space-y-6 font-mono">
      <Card className="bg-[#060B18]/60 border-[#1F2937]/60 shadow-2xl">
        <CardHeader>
          <CardTitle className="text-xs font-mono uppercase tracking-wider text-slate-400 flex items-center justify-between">
            <span className="flex items-center">
              <ShieldCheck className="h-4 w-4 text-[#D4AF37] mr-2" />
              ACCESS CONTROL — USER MANAGEMENT
            </span>
            <button
              onClick={() => { setCreateOpen(true); setCreateError(null); }}
              className="flex items-center space-x-1.5 bg-[#D4AF37] hover:bg-[#F3C63F] text-[#030712] font-bold text-[10px] uppercase tracking-wider rounded px-3 py-1.5"
            >
              <UserPlus className="h-3.5 w-3.5" />
              <span>Create User</span>
            </button>
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader className="border-[#1F2937]/40 bg-[#030712]/50">
              <TableRow className="border-[#1F2937]/40">
                <TableHead className="text-slate-500 font-mono text-[10px]">EMAIL</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-center">ROLE</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-center">STATUS</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px]">ASSIGNED CLIENTS</TableHead>
                <TableHead className="text-slate-500 font-mono text-[10px] text-right">ACTION</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id} className="border-[#1F2937]/40 hover:bg-[#060B18] transition-colors">
                  <TableCell className="font-mono text-xs font-bold text-slate-200">{u.email}</TableCell>
                  <TableCell className="text-center">
                    <Badge className={`font-mono text-[8px] ${
                      u.role === "super_admin"
                        ? "bg-[#D4AF37]/10 text-[#D4AF37] border border-[#D4AF37]/30"
                        : "bg-blue-500/10 text-blue-400 border border-blue-500/20"
                    }`}>
                      {u.role.toUpperCase()}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-center">
                    {u.is_active ? (
                      <Badge className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono text-[8px]">ACTIVE</Badge>
                    ) : (
                      <Badge className="bg-slate-500/10 text-slate-400 border border-slate-500/20 font-mono text-[8px]">INACTIVE</Badge>
                    )}
                  </TableCell>
                  <TableCell className="font-mono text-[10px] text-slate-400">
                    {u.role === "super_admin" ? (
                      <span className="text-[#D4AF37]/70">All clients</span>
                    ) : u.client_ids.length === 0 ? (
                      <span className="text-slate-600">None assigned</span>
                    ) : (
                      u.client_ids.map((id) => clientName(id)).join(", ")
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end space-x-3">
                      <button
                        onClick={() => { setResetTarget(u); setResetError(null); }}
                        className="flex items-center space-x-1 text-[#38BDF8] hover:text-[#38BDF8]/80 text-[10px] uppercase"
                        title="Reset password"
                      >
                        <KeyRound className="h-3 w-3" />
                        <span>Reset</span>
                      </button>
                      <button
                        onClick={() => { setDeleteTarget(u); setDeleteError(null); }}
                        className="flex items-center space-x-1 text-red-400 hover:text-red-300 text-[10px] uppercase"
                        title="Delete user"
                      >
                        <Trash2 className="h-3 w-3" />
                        <span>Delete</span>
                      </button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
              {users.length === 0 && (
                <TableRow>
                  <TableCell colSpan={5} className="text-center py-10 text-slate-500 font-mono text-xs">
                    No users provisioned yet.
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Create User Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="bg-[#060B18] border-[#1F2937] text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-mono text-[#D4AF37]">Create User</DialogTitle>
            <DialogDescription className="text-slate-400 font-mono text-xs">
              A password is generated automatically and shown once after creation — hand it to the user yourself.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2 font-mono text-xs">
            <div className="space-y-2">
              <label className="text-slate-400">Email</label>
              <input
                type="email"
                placeholder="name@company.com"
                value={createEmail}
                onChange={(e) => setCreateEmail(e.target.value)}
                className="w-full bg-[#030712] border border-[#1F2937] rounded px-3 py-2 text-slate-100 focus:outline-none focus:border-[#D4AF37]"
              />
            </div>
            <div className="space-y-2">
              <label className="text-slate-400">Role</label>
              <select
                value={createRole}
                onChange={(e) => setCreateRole(e.target.value as "client_user" | "super_admin")}
                className="w-full bg-[#030712] border border-[#1F2937] rounded px-3 py-2 text-slate-100 focus:outline-none focus:border-[#D4AF37]"
              >
                <option value="client_user">Client User</option>
                <option value="super_admin">Super Admin</option>
              </select>
            </div>
            {createRole === "client_user" && (
              <div className="space-y-2">
                <label className="text-slate-400">Assigned Clients</label>
                <div className="max-h-40 overflow-y-auto border border-[#1F2937] rounded p-2 space-y-1 bg-[#030712]">
                  {clients.map((c: any) => (
                    <label key={c.id} className="flex items-center space-x-2 text-slate-300 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={createClientIds.includes(c.id)}
                        onChange={() => toggleCreateClient(c.id)}
                        className="accent-[#D4AF37]"
                      />
                      <span>{c.name}</span>
                    </label>
                  ))}
                  {clients.length === 0 && (
                    <span className="text-slate-600 text-[10px]">No clients available.</span>
                  )}
                </div>
              </div>
            )}
            {createError && <p className="text-red-500 text-[11px]">{createError}</p>}
          </div>
          <DialogFooter>
            <button
              onClick={() => setCreateOpen(false)}
              className="font-mono text-xs px-4 py-2 text-slate-400 hover:text-slate-200"
            >
              Cancel
            </button>
            <button
              onClick={handleCreate}
              disabled={createLoading}
              className="bg-[#D4AF37] text-black font-bold font-mono text-xs px-4 py-2 rounded disabled:opacity-50 flex items-center space-x-2"
            >
              {createLoading && <Loader2 className="h-3 w-3 animate-spin" />}
              <span>{createLoading ? "Creating..." : "Create User"}</span>
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reset Password Confirmation Dialog */}
      <Dialog open={resetTarget !== null} onOpenChange={(open) => { if (!open) { setResetTarget(null); setResetError(null); } }}>
        <DialogContent className="bg-[#060B18] border-[#1F2937] text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-mono text-[#38BDF8]">Reset Password</DialogTitle>
            <DialogDescription className="text-slate-400 font-mono text-xs">
              Generate a new password for{" "}
              <span className="text-slate-200 font-bold">{resetTarget?.email}</span>? Their current password stops working immediately.
            </DialogDescription>
          </DialogHeader>
          {resetError && (
            <p className="text-red-500 text-[11px]">{resetError}</p>
          )}
          <DialogFooter>
            <button
              onClick={() => { setResetTarget(null); setResetError(null); }}
              className="font-mono text-xs px-4 py-2 text-slate-300 hover:text-white"
            >
              Cancel
            </button>
            <button
              onClick={handleResetPassword}
              disabled={resetLoading}
              className="bg-[#38BDF8] text-black font-bold font-mono text-xs px-4 py-2 rounded disabled:opacity-50"
            >
              {resetLoading ? "Resetting..." : "Reset Password"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={deleteTarget !== null} onOpenChange={(open) => { if (!open) { setDeleteTarget(null); setDeleteError(null); } }}>
        <DialogContent className="bg-[#060B18] border-[#1F2937] text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-mono text-red-500">Delete User</DialogTitle>
            <DialogDescription className="text-slate-400 font-mono text-xs">
              Are you sure you want to permanently delete{" "}
              <span className="text-slate-200 font-bold">{deleteTarget?.email}</span>? This action is irreversible.
            </DialogDescription>
          </DialogHeader>
          {deleteError && (
            <p className="text-red-500 text-[11px]">{deleteError}</p>
          )}
          <DialogFooter>
            <button
              onClick={() => { setDeleteTarget(null); setDeleteError(null); }}
              className="font-mono text-xs px-4 py-2 text-slate-300 hover:text-white"
            >
              Cancel
            </button>
            <button
              onClick={handleDelete}
              disabled={deleteLoading}
              className="bg-red-600 text-white hover:bg-red-700 font-mono text-xs px-4 py-2 rounded-md disabled:opacity-50"
            >
              {deleteLoading ? "Deleting..." : "Delete"}
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* One-Time Password Reveal Dialog (after create or reset) */}
      <Dialog open={passwordReveal !== null} onOpenChange={(open) => { if (!open) { setPasswordReveal(null); setCopied(false); } }}>
        <DialogContent className="bg-[#060B18] border-[#D4AF37]/40 text-slate-100">
          <DialogHeader>
            <DialogTitle className="font-mono text-[#D4AF37] flex items-center">
              <KeyRound className="h-4 w-4 mr-2" />
              Password Generated
            </DialogTitle>
            <DialogDescription className="text-slate-400 font-mono text-xs">
              For <span className="text-slate-200 font-bold">{passwordReveal?.email}</span>. Copy this now — it will not be shown again.
            </DialogDescription>
          </DialogHeader>
          <div className="py-2">
            <div className="flex items-center space-x-2 bg-[#030712] border border-[#1F2937] rounded p-3">
              <code className="flex-1 text-sm text-emerald-400 break-all font-mono">{passwordReveal?.password}</code>
              <button
                onClick={handleCopyPassword}
                title="Copy password"
                className="shrink-0 text-slate-400 hover:text-[#D4AF37] transition-colors"
              >
                {copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>
          </div>
          <DialogFooter>
            <button
              onClick={() => { setPasswordReveal(null); setCopied(false); }}
              className="bg-[#D4AF37] text-black font-bold font-mono text-xs px-4 py-2 rounded"
            >
              Done
            </button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
