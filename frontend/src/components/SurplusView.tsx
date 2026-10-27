import React, { useState, useEffect } from 'react';
import {
  HeartHandshake,
  Plus,
  Search,
  Filter,
  CheckCircle2,
  XCircle,
  Clock,
  MapPin,
  ShieldCheck,
  AlertTriangle,
  Truck,
  Building,
  RefreshCw,
  Eye,
  Award,
  Bell,
  Check,
  ChevronRight,
  Package,
  Calendar,
  Phone,
  AlertCircle,
  CheckCheck,
  Navigation,
} from 'lucide-react';
import {
  SurplusListing,
  SurplusClaim,
  NgoMatchRecommendation,
  SurplusMatchesResponse,
  NgoProfile,
  SurplusNotification,
  InventoryItem,
  PickupSchedule,
  PickupScheduleCreatePayload,
  PickupScheduleReschedulePayload,
} from '../types';
import { api } from '../services/api';

interface SurplusViewProps {
  currentTenantId?: string;
  userRole?: string;
}

export const SurplusView: React.FC<SurplusViewProps> = ({ currentTenantId, userRole }) => {
  // Mode selection: 'donor' (Business View) or 'ngo' (NGO Marketplace)
  const [viewMode, setViewMode] = useState<'donor' | 'ngo'>('donor');

  // Listings State
  const [listings, setListings] = useState<SurplusListing[]>([]);
  const [totalListings, setTotalListings] = useState<number>(0);
  const [loading, setLoading] = useState<boolean>(true);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const [storageFilter, setStorageFilter] = useState<string>('');
  const [inventoryItems, setInventoryItems] = useState<InventoryItem[]>([]);

  // Matching Engine Modal State
  const [matchingListing, setMatchingListing] = useState<SurplusListing | null>(null);
  const [matchResults, setMatchResults] = useState<SurplusMatchesResponse | null>(null);
  const [loadingMatches, setLoadingMatches] = useState<boolean>(false);

  // Claims Modal State (for Donor to review incoming claims)
  const [claimsListing, setClaimsListing] = useState<SurplusListing | null>(null);
  const [listingClaims, setListingClaims] = useState<SurplusClaim[]>([]);
  const [loadingClaims, setLoadingClaims] = useState<boolean>(false);
  const [rejectingClaimId, setRejectingClaimId] = useState<string | null>(null);
  const [rejectionReason, setRejectionReason] = useState<string>('');

  // Pickup Scheduling & Rescheduling Modal State (Milestone 3 - Phase 2)
  const [schedulingClaim, setSchedulingClaim] = useState<SurplusClaim | null>(null);
  const [reschedulingClaim, setReschedulingClaim] = useState<SurplusClaim | null>(null);
  const [schedDate, setSchedDate] = useState<string>('');
  const [schedStartTime, setSchedStartTime] = useState<string>('');
  const [schedEndTime, setSchedEndTime] = useState<string>('');
  const [schedLocation, setSchedLocation] = useState<string>('');
  const [schedInstructions, setSchedInstructions] = useState<string>('');
  const [schedVehicleType, setSchedVehicleType] = useState<string>('VAN');
  const [schedDriverName, setSchedDriverName] = useState<string>('');
  const [schedDriverPhone, setSchedDriverPhone] = useState<string>('');
  const [reschedReason, setReschedReason] = useState<string>('');
  const [scheduleLoading, setScheduleLoading] = useState<boolean>(false);

  // NGO View State (My Claims)
  const [myClaims, setMyClaims] = useState<SurplusClaim[]>([]);
  const [claimingListing, setClaimingListing] = useState<SurplusListing | null>(null);
  const [claimQty, setClaimQty] = useState<number>(10);
  const [claimNotes, setClaimNotes] = useState<string>('');
  const [claimPickupTime, setClaimPickupTime] = useState<string>('');
  const [submittingClaim, setSubmittingClaim] = useState<boolean>(false);

  // Create Listing Modal State
  const [showCreateModal, setShowCreateModal] = useState<boolean>(false);
  const [selectedItemId, setSelectedItemId] = useState<string>('');
  const [listingTitle, setListingTitle] = useState<string>('');
  const [listingQty, setListingQty] = useState<number>(10);
  const [pickupAddress, setPickupAddress] = useState<string>('Main Store Front, Loading Bay 2');
  const [pickupInstructions, setPickupInstructions] = useState<string>('Bring insulated coolers for cold items.');
  const [availableUntil, setAvailableUntil] = useState<string>('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [creatingListing, setCreatingListing] = useState<boolean>(false);

  // NGO Profile State
  const [showProfileModal, setShowProfileModal] = useState<boolean>(false);
  const [ngoProfile, setNgoProfile] = useState<NgoProfile | null>(null);
  const [profileSaving, setProfileSaving] = useState<boolean>(false);

  // Notifications
  const [notifications, setNotifications] = useState<SurplusNotification[]>([]);
  const [showNotifications, setShowNotifications] = useState<boolean>(false);

  // Status message / toast
  const [bannerMessage, setBannerMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  const showToast = (text: string, type: 'success' | 'error' = 'success') => {
    setBannerMessage({ text, type });
    setTimeout(() => setBannerMessage(null), 5000);
  };

  // 1. Load Listings & Data
  const loadData = async () => {
    setLoading(true);
    try {
      // Load listings
      const res = await api.listSurplusListings({
        status: statusFilter || undefined,
        storage_requirement: storageFilter || undefined,
        size: 50,
      });
      setListings(res.data);
      setTotalListings(res.pagination.total);

      // Load inventory items for the listing creator
      const invRes = await api.listInventory({ size: 100 });
      setInventoryItems(invRes.data);

      // Load my claims (for NGO portal)
      try {
        const claims = await api.getMyClaims();
        setMyClaims(claims);
      } catch {
        // Not an NGO or unauthenticated
      }

      // Load notifications
      try {
        const notifs = await api.getSurplusNotifications();
        setNotifications(notifs);
      } catch {
        // Ignored
      }
    } catch (err: any) {
      console.error('Failed to load surplus data:', err);
      showToast(err.message || 'Failed to load surplus listings', 'error');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [statusFilter, storageFilter, viewMode]);

  // Set default available_until to tomorrow 18:00
  useEffect(() => {
    const tmrw = new Date();
    tmrw.setDate(tmrw.getDate() + 1);
    tmrw.setHours(18, 0, 0, 0);
    setAvailableUntil(tmrw.toISOString().slice(0, 16));
  }, []);

  // 2. Fetch Matching NGOs for a listing
  const handleOpenMatches = async (listing: SurplusListing) => {
    setMatchingListing(listing);
    setLoadingMatches(true);
    try {
      const results = await api.getNgoMatchesForListing(listing.id);
      setMatchResults(results);
    } catch (err: any) {
      showToast(err.message || 'Failed to calculate NGO matches', 'error');
    } finally {
      setLoadingMatches(false);
    }
  };

  // 3. Open Claims Review Modal (for donor)
  const handleOpenClaims = async (listing: SurplusListing) => {
    setClaimsListing(listing);
    setLoadingClaims(true);
    try {
      const claims = await api.getListingClaims(listing.id);
      setListingClaims(claims);
    } catch (err: any) {
      showToast(err.message || 'Failed to load claims', 'error');
    } finally {
      setLoadingClaims(false);
    }
  };

  // 4. Review Claim (Approve / Reject)
  const handleReviewClaim = async (claimId: string, action: 'APPROVE' | 'REJECT') => {
    try {
      await api.reviewClaim(claimId, action, rejectionReason || undefined);
      showToast(`Claim successfully ${action === 'APPROVE' ? 'approved' : 'rejected'}`);
      setRejectingClaimId(null);
      setRejectionReason('');
      if (claimsListing) {
        handleOpenClaims(claimsListing);
      }
      loadData();
    } catch (err: any) {
      showToast(err.message || `Failed to ${action} claim`, 'error');
    }
  };

  // 5. Complete Physical Handover (Deduct Stock)
  const handleCompleteHandover = async (claimId: string) => {
    try {
      await api.completeClaimTransfer(claimId);
      showToast('Pickup confirmed! Physical inventory ledger automatically adjusted via DONATION_DISPATCH.');
      if (claimsListing) {
        handleOpenClaims(claimsListing);
      }
      loadData();
    } catch (err: any) {
      showToast(err.message || 'Failed to complete handover', 'error');
    }
  };

  // 5b. Pickup Logistics & Milestone Handlers (Phase 2)
  const handleOpenSchedule = (claim: SurplusClaim) => {
    setSchedulingClaim(claim);
    const tmrw = new Date();
    tmrw.setDate(tmrw.getDate() + 1);
    const dateStr = tmrw.toISOString().slice(0, 10);
    setSchedDate(dateStr);

    const start = new Date(tmrw);
    start.setHours(10, 0, 0, 0);
    const end = new Date(tmrw);
    end.setHours(12, 0, 0, 0);
    setSchedStartTime(start.toISOString().slice(0, 16));
    setSchedEndTime(end.toISOString().slice(0, 16));

    setSchedLocation('Loading Bay 2, Warehouse Dock');
    setSchedInstructions('Bring thermal blankets / coolers for perishables.');
    setSchedVehicleType('VAN');
    setSchedDriverName('');
    setSchedDriverPhone('');
  };

  const handleSaveSchedule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!schedulingClaim) return;
    if (new Date(schedEndTime) <= new Date(schedStartTime)) {
      showToast('Pickup end time must be strictly after start time', 'error');
      return;
    }
    setScheduleLoading(true);
    try {
      await api.schedulePickup(schedulingClaim.id, {
        pickup_date: schedDate,
        pickup_start_time: new Date(schedStartTime).toISOString(),
        pickup_end_time: new Date(schedEndTime).toISOString(),
        pickup_location: schedLocation,
        pickup_instructions: schedInstructions || undefined,
        vehicle_type: schedVehicleType || undefined,
        driver_name: schedDriverName || undefined,
        driver_phone: schedDriverPhone || undefined,
      });
      showToast('Pickup window scheduled successfully! Food donor notified.');
      setSchedulingClaim(null);
      if (claimsListing) {
        handleOpenClaims(claimsListing);
      }
      loadData();
    } catch (err: any) {
      showToast(err.message || 'Failed to schedule pickup', 'error');
    } finally {
      setScheduleLoading(false);
    }
  };

  const handleOpenReschedule = (claim: SurplusClaim) => {
    setReschedulingClaim(claim);
    const sched = claim.pickup_schedule;
    if (sched) {
      setSchedDate(sched.pickup_date);
      setSchedStartTime(new Date(sched.pickup_start_time).toISOString().slice(0, 16));
      setSchedEndTime(new Date(sched.pickup_end_time).toISOString().slice(0, 16));
      setSchedLocation(sched.pickup_location);
      setSchedInstructions(sched.pickup_instructions || '');
      setSchedVehicleType(sched.vehicle_type || 'VAN');
      setSchedDriverName(sched.driver_name || '');
      setSchedDriverPhone(sched.driver_phone || '');
    } else {
      const tmrw = new Date();
      tmrw.setDate(tmrw.getDate() + 2);
      setSchedDate(tmrw.toISOString().slice(0, 10));
      const s = new Date(tmrw);
      s.setHours(14, 0, 0, 0);
      const e = new Date(tmrw);
      e.setHours(16, 0, 0, 0);
      setSchedStartTime(s.toISOString().slice(0, 16));
      setSchedEndTime(e.toISOString().slice(0, 16));
    }
    setReschedReason('');
  };

  const handleSaveReschedule = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reschedulingClaim) return;
    if (!reschedReason.trim()) {
      showToast('A documented reschedule reason is required', 'error');
      return;
    }
    if (new Date(schedEndTime) <= new Date(schedStartTime)) {
      showToast('Pickup end time must be strictly after start time', 'error');
      return;
    }
    setScheduleLoading(true);
    try {
      await api.reschedulePickup(reschedulingClaim.id, {
        pickup_date: schedDate,
        pickup_start_time: new Date(schedStartTime).toISOString(),
        pickup_end_time: new Date(schedEndTime).toISOString(),
        rescheduled_reason: reschedReason,
        pickup_location: schedLocation || undefined,
        pickup_instructions: schedInstructions || undefined,
        vehicle_type: schedVehicleType || undefined,
        driver_name: schedDriverName || undefined,
        driver_phone: schedDriverPhone || undefined,
      });
      showToast('Pickup rescheduled successfully. Counterpart notified.');
      setReschedulingClaim(null);
      if (claimsListing) {
        handleOpenClaims(claimsListing);
      }
      loadData();
    } catch (err: any) {
      showToast(err.message || 'Failed to reschedule pickup', 'error');
    } finally {
      setScheduleLoading(false);
    }
  };

  const handleMarkReady = async (claimId: string) => {
    try {
      await api.markPickupReady(claimId);
      showToast('Food marked ready for collection! Recipient NGO notified.');
      if (claimsListing) {
        handleOpenClaims(claimsListing);
      }
      loadData();
    } catch (err: any) {
      showToast(err.message || 'Failed to mark ready', 'error');
    }
  };

  const handleConfirmCollection = async (claimId: string) => {
    try {
      await api.confirmPickupCollection(claimId);
      showToast('Collection underway! Food items in transit to recipient facility.');
      if (claimsListing) {
        handleOpenClaims(claimsListing);
      }
      loadData();
    } catch (err: any) {
      showToast(err.message || 'Failed to confirm collection', 'error');
    }
  };

  const handleMarkMissed = async (claimId: string) => {
    const reason = window.prompt('Enter reason for missed pickup window:');
    if (reason === null) return;
    try {
      await api.markPickupMissed(claimId, reason || undefined);
      showToast('Pickup marked as missed. Recipient NGO alerted to reschedule.');
      if (claimsListing) {
        handleOpenClaims(claimsListing);
      }
      loadData();
    } catch (err: any) {
      showToast(err.message || 'Failed to mark missed', 'error');
    }
  };

  const handleMarkAllRead = async () => {
    try {
      const count = await api.markAllNotificationsRead();
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      showToast(`Marked ${count} notifications as read.`);
    } catch (err: any) {
      showToast(err.message || 'Failed to mark notifications read', 'error');
    }
  };

  // 6. Cancel Listing
  const handleCancelListing = async (listingId: string) => {
    if (!window.confirm('Are you sure you want to cancel this surplus listing? Reserved allocations will be released.')) {
      return;
    }
    try {
      await api.cancelSurplusListing(listingId, 'Cancelled by donor');
      showToast('Surplus listing cancelled and reserved inventory restored to commercial stock.');
      loadData();
    } catch (err: any) {
      showToast(err.message || 'Failed to cancel listing', 'error');
    }
  };

  // 7. Submit Claim (from NGO)
  const handleSubmitClaim = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!claimingListing) return;

    setSubmittingClaim(true);
    try {
      await api.createSurplusClaim({
        listing_id: claimingListing.id,
        claimed_quantity: claimQty,
        pickup_time: claimPickupTime ? new Date(claimPickupTime).toISOString() : undefined,
        notes: claimNotes || undefined,
      });
      showToast(`Claim submitted for ${claimQty} ${claimingListing.unit} of ${claimingListing.product_name}! Donor notified.`);
      setClaimingListing(null);
      setClaimNotes('');
      loadData();
    } catch (err: any) {
      showToast(err.message || 'Failed to submit claim', 'error');
    } finally {
      setSubmittingClaim(false);
    }
  };

  // 8. Create Listing
  const handleCreateListing = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedItemId) {
      setCreateError('Please select an inventory item.');
      return;
    }
    if (listingQty <= 0) {
      setCreateError('Quantity must be greater than zero.');
      return;
    }
    if (!availableUntil) {
      setCreateError('Please select available until date/time.');
      return;
    }

    setCreatingListing(true);
    setCreateError(null);
    try {
      const selectedItem = inventoryItems.find((i) => i.id === selectedItemId);
      await api.createSurplusListing({
        item_id: selectedItemId,
        title: listingTitle || (selectedItem ? `Surplus ${selectedItem.name}` : undefined),
        quantity: listingQty,
        pickup_address: pickupAddress,
        pickup_instructions: pickupInstructions || undefined,
        available_until: new Date(availableUntil).toISOString(),
      });
      showToast('Surplus listing created successfully! Matched NGOs can now reserve this donation.');
      setShowCreateModal(false);
      setSelectedItemId('');
      setListingTitle('');
      loadData();
    } catch (err: any) {
      setCreateError(err.message || 'Failed to create surplus listing');
    } finally {
      setCreatingListing(false);
    }
  };

  // 9. Load NGO Profile
  const handleOpenNgoProfile = async () => {
    setShowProfileModal(true);
    try {
      const profile = await api.getNgoProfile();
      setNgoProfile(profile);
    } catch (err: any) {
      showToast(err.message || 'Failed to load NGO profile', 'error');
    }
  };

  // 10. Save NGO Profile
  const handleSaveNgoProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ngoProfile) return;
    setProfileSaving(true);
    try {
      const updated = await api.updateNgoProfile({
        organization_type: ngoProfile.organization_type,
        contact_person: ngoProfile.contact_person,
        contact_phone: ngoProfile.contact_phone,
        contact_email: ngoProfile.contact_email,
        address: ngoProfile.address,
        latitude: ngoProfile.latitude,
        longitude: ngoProfile.longitude,
        service_radius_km: ngoProfile.service_radius_km,
        max_capacity_units: ngoProfile.max_capacity_units,
        accepted_categories: ngoProfile.accepted_categories,
        storage_facilities: ngoProfile.storage_facilities,
      });
      setNgoProfile(updated);
      showToast('NGO operational profile updated successfully!');
      setShowProfileModal(false);
    } catch (err: any) {
      showToast(err.message || 'Failed to update NGO profile', 'error');
    } finally {
      setProfileSaving(false);
    }
  };

  // Active / selected item helper
  const selectedItemData = inventoryItems.find((i) => i.id === selectedItemId);

  return (
    <div className="surplus-container" style={{ padding: '24px', maxWidth: '1400px', margin: '0 auto' }}>
      {/* Toast Alert Banner */}
      {bannerMessage && (
        <div
          style={{
            marginBottom: '16px',
            padding: '12px 16px',
            borderRadius: '8px',
            background: bannerMessage.type === 'success' ? '#ECFDF5' : '#FEF2F2',
            color: bannerMessage.type === 'success' ? '#065F46' : '#991B1B',
            border: `1px solid ${bannerMessage.type === 'success' ? '#A7F3D0' : '#FECACA'}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            {bannerMessage.type === 'success' ? <CheckCircle2 size={18} /> : <AlertTriangle size={18} />}
            <span>{bannerMessage.text}</span>
          </div>
          <button
            onClick={() => setBannerMessage(null)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}
          >
            ×
          </button>
        </div>
      )}

      {/* Main Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px', flexWrap: 'wrap', gap: '16px' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <HeartHandshake size={28} color="var(--primary)" />
            <h1 style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-900)' }}>
              Surplus Redistribution & NGO Matching
            </h1>
          </div>
          <p style={{ color: 'var(--gray-500)', fontSize: '0.875rem', marginTop: '4px' }}>
            Milestone 3 — Connect retail surplus food inventory to verified community pantries, soup kitchens, and charities.
          </p>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          {/* Persona Switcher (Donor vs NGO Marketplace) */}
          <div style={{ display: 'flex', background: 'var(--gray-100)', padding: '4px', borderRadius: '8px' }}>
            <button
              onClick={() => setViewMode('donor')}
              style={{
                padding: '6px 14px',
                borderRadius: '6px',
                border: 'none',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '0.8125rem',
                background: viewMode === 'donor' ? '#ffffff' : 'transparent',
                color: viewMode === 'donor' ? 'var(--primary)' : 'var(--gray-600)',
                boxShadow: viewMode === 'donor' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              }}
            >
              🏢 Business Donor View
            </button>
            <button
              onClick={() => setViewMode('ngo')}
              style={{
                padding: '6px 14px',
                borderRadius: '6px',
                border: 'none',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '0.8125rem',
                background: viewMode === 'ngo' ? '#ffffff' : 'transparent',
                color: viewMode === 'ngo' ? 'var(--primary)' : 'var(--gray-600)',
                boxShadow: viewMode === 'ngo' ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
              }}
            >
              🍲 NGO Rescue Marketplace
            </button>
          </div>

          {/* Notifications Button */}
          <div style={{ position: 'relative' }}>
            <button
              onClick={() => setShowNotifications(!showNotifications)}
              className="btn btn-secondary"
              style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '8px 12px' }}
              title="Surplus Notifications"
            >
              <Bell size={16} />
              {notifications.filter((n) => !n.is_read).length > 0 && (
                <span
                  style={{
                    background: '#EF4444',
                    color: '#ffffff',
                    fontSize: '0.75rem',
                    fontWeight: 700,
                    borderRadius: '9999px',
                    padding: '1px 6px',
                  }}
                >
                  {notifications.filter((n) => !n.is_read).length}
                </span>
              )}
            </button>

            {/* Notification Popover */}
            {showNotifications && (
              <div
                style={{
                  position: 'absolute',
                  right: 0,
                  top: '42px',
                  width: '320px',
                  background: '#ffffff',
                  boxShadow: '0 10px 25px -5px rgba(0,0,0,0.15)',
                  borderRadius: '8px',
                  border: '1px solid var(--border)',
                  zIndex: 50,
                  maxHeight: '380px',
                  overflowY: 'auto',
                }}
              >
                <div style={{ padding: '12px', borderBottom: '1px solid var(--border)', fontWeight: 600, fontSize: '0.875rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>Surplus Alerts & Events</span>
                  {notifications.some((n) => !n.is_read) && (
                    <button
                      onClick={handleMarkAllRead}
                      style={{ fontSize: '0.75rem', color: 'var(--primary)', background: 'none', border: 'none', cursor: 'pointer', fontWeight: 500 }}
                    >
                      Mark all read
                    </button>
                  )}
                </div>
                {notifications.length === 0 ? (
                  <div style={{ padding: '16px', textAlign: 'center', color: 'var(--gray-400)', fontSize: '0.8125rem' }}>
                    No notifications yet.
                  </div>
                ) : (
                  notifications.map((n) => (
                    <div
                      key={n.id}
                      onClick={async () => {
                        if (!n.is_read) {
                          await api.markNotificationRead(n.id);
                          setNotifications((prev) => prev.map((item) => (item.id === n.id ? { ...item, is_read: true } : item)));
                        }
                      }}
                      style={{
                        padding: '10px 12px',
                        borderBottom: '1px solid var(--border)',
                        background: n.is_read ? '#ffffff' : '#F0FDF4',
                        cursor: n.is_read ? 'default' : 'pointer',
                      }}
                    >
                      <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--gray-900)' }}>{n.title}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--gray-600)', marginTop: '2px' }}>{n.message}</div>
                      <div style={{ fontSize: '0.6875rem', color: 'var(--gray-400)', marginTop: '4px' }}>
                        {new Date(n.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                      </div>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>

          {/* Action Trigger based on mode */}
          {viewMode === 'donor' ? (
            <button
              onClick={() => setShowCreateModal(true)}
              className="btn btn-primary"
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Plus size={16} />
              <span>Create Surplus Listing</span>
            </button>
          ) : (
            <button
              onClick={handleOpenNgoProfile}
              className="btn btn-secondary"
              style={{ display: 'flex', alignItems: 'center', gap: '6px' }}
            >
              <Building size={16} />
              <span>Configure NGO Capabilities</span>
            </button>
          )}

          <button
            onClick={loadData}
            className="btn btn-secondary"
            title="Refresh Listings"
            style={{ padding: '8px 12px' }}
          >
            <RefreshCw size={16} className={loading ? 'animate-spin' : ''} />
          </button>
        </div>
      </div>

      {/* Metrics Row (for Donor View) */}
      {viewMode === 'donor' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '16px', marginBottom: '24px' }}>
          <div className="card" style={{ padding: '16px', borderLeft: '4px solid var(--primary)' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', textTransform: 'uppercase', fontWeight: 600 }}>
              Active Donations Earmarked
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-900)', marginTop: '4px' }}>
              {listings.filter((l) => l.status === 'AVAILABLE' || l.status === 'RESERVED').length}
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--primary)', marginTop: '4px' }}>
              Stock protected from oversubscription
            </div>
          </div>

          <div className="card" style={{ padding: '16px', borderLeft: '4px solid #F59E0B' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', textTransform: 'uppercase', fontWeight: 600 }}>
              Pending NGO Claims
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-900)', marginTop: '4px' }}>
              {listings.reduce((acc, l) => acc + (l.claims_count || 0), 0)}
            </div>
            <div style={{ fontSize: '0.75rem', color: '#D97706', marginTop: '4px' }}>
              Awaiting donor review & handover
            </div>
          </div>

          <div className="card" style={{ padding: '16px', borderLeft: '4px solid #10B981' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', textTransform: 'uppercase', fontWeight: 600 }}>
              Completed Handover Dispatches
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-900)', marginTop: '4px' }}>
              {listings.filter((l) => l.status === 'COMPLETED').length}
            </div>
            <div style={{ fontSize: '0.75rem', color: '#059669', marginTop: '4px' }}>
              Ledger verified stock deductions
            </div>
          </div>

          <div className="card" style={{ padding: '16px', borderLeft: '4px solid #EF4444' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', textTransform: 'uppercase', fontWeight: 600 }}>
              Imminent Expiry (&lt; 24h)
            </div>
            <div style={{ fontSize: '1.5rem', fontWeight: 700, color: 'var(--gray-900)', marginTop: '4px' }}>
              {listings.filter((l) => l.days_to_expiry <= 1 && l.status === 'AVAILABLE').length}
            </div>
            <div style={{ fontSize: '0.75rem', color: '#DC2626', marginTop: '4px' }}>
              Critical priority rescue batches
            </div>
          </div>
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="card" style={{ padding: '16px', marginBottom: '24px' }}>
        <div style={{ display: 'flex', gap: '16px', alignItems: 'center', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '220px' }}>
            <Filter size={16} color="var(--gray-500)" />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="form-select"
              style={{ fontSize: '0.8125rem' }}
            >
              <option value="">All Statuses</option>
              <option value="AVAILABLE">Available for Rescue</option>
              <option value="RESERVED">Reserved (Claim Pending)</option>
              <option value="COMPLETED">Completed Handover</option>
              <option value="CANCELLED">Cancelled</option>
            </select>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: '220px' }}>
            <span style={{ fontSize: '0.8125rem', color: 'var(--gray-600)', fontWeight: 500 }}>Storage:</span>
            <select
              value={storageFilter}
              onChange={(e) => setStorageFilter(e.target.value)}
              className="form-select"
              style={{ fontSize: '0.8125rem' }}
            >
              <option value="">All Storage Modes</option>
              <option value="AMBIENT">Ambient / Dry</option>
              <option value="REFRIGERATED">Refrigerated (Cold Chain)</option>
              <option value="FROZEN">Frozen</option>
            </select>
          </div>

          <div style={{ marginLeft: 'auto', fontSize: '0.8125rem', color: 'var(--gray-500)' }}>
            Showing <strong>{listings.length}</strong> of <strong>{totalListings}</strong> listings
          </div>
        </div>
      </div>

      {/* Listings Section */}
      {viewMode === 'donor' ? (
        /* DONOR TABLE VIEW */
        <div className="card" style={{ overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid var(--border)', fontWeight: 600, color: 'var(--gray-900)' }}>
            My Active Surplus Donation Batches
          </div>
          {loading ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--gray-500)' }}>
              Loading surplus listings...
            </div>
          ) : listings.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', color: 'var(--gray-500)' }}>
              <Package size={40} style={{ margin: '0 auto 12px', opacity: 0.4 }} />
              <div>No surplus listings found.</div>
              <p style={{ fontSize: '0.8125rem', marginTop: '4px' }}>
                Create a surplus listing from your inventory stock to match with eligible recipient NGOs.
              </p>
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table className="table" style={{ width: '100%', borderCollapse: 'collapse' }}>
                <thead>
                  <tr style={{ background: 'var(--gray-50)', textAlign: 'left', borderBottom: '1px solid var(--border)' }}>
                    <th style={{ padding: '12px 16px' }}>Item & Title</th>
                    <th style={{ padding: '12px 16px' }}>Category</th>
                    <th style={{ padding: '12px 16px' }}>Earmarked / Available</th>
                    <th style={{ padding: '12px 16px' }}>Expiry & Urgency</th>
                    <th style={{ padding: '12px 16px' }}>Storage</th>
                    <th style={{ padding: '12px 16px' }}>Status</th>
                    <th style={{ padding: '12px 16px', textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {listings.map((listing) => (
                    <tr key={listing.id} style={{ borderBottom: '1px solid var(--border)' }}>
                      <td style={{ padding: '12px 16px' }}>
                        <div style={{ fontWeight: 600, color: 'var(--gray-900)' }}>
                          {listing.title || listing.product_name}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                          Product: {listing.product_name} • SKU: {listing.sku || 'N/A'}
                        </div>
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <span className="badge badge-secondary">{listing.category_name}</span>
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <div style={{ fontWeight: 600 }}>
                          {listing.remaining_claimable_quantity} / {listing.quantity} {listing.unit}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                          {listing.claims_count} active claims
                        </div>
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <Clock size={14} color={listing.days_to_expiry <= 1 ? '#EF4444' : '#6B7280'} />
                          <span
                            style={{
                              fontSize: '0.8125rem',
                              fontWeight: 600,
                              color: listing.days_to_expiry <= 1 ? '#EF4444' : 'inherit',
                            }}
                          >
                            {listing.days_to_expiry <= 0
                              ? 'Expires today'
                              : `${listing.days_to_expiry.toFixed(0)} days left`}
                          </span>
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                          {listing.expiry_date}
                        </div>
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <span
                          style={{
                            fontSize: '0.75rem',
                            padding: '2px 8px',
                            borderRadius: '4px',
                            background: listing.storage_requirement === 'REFRIGERATED' ? '#DBEAFE' : '#F3F4F6',
                            color: listing.storage_requirement === 'REFRIGERATED' ? '#1E40AF' : '#374151',
                            fontWeight: 600,
                          }}
                        >
                          {listing.storage_requirement}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px' }}>
                        <span
                          style={{
                            fontSize: '0.75rem',
                            padding: '3px 8px',
                            borderRadius: '9999px',
                            fontWeight: 600,
                            background:
                              listing.status === 'AVAILABLE'
                                ? '#D1FAE5'
                                : listing.status === 'RESERVED'
                                ? '#FEF3C7'
                                : listing.status === 'COMPLETED'
                                ? '#E0E7FF'
                                : '#FEE2E2',
                            color:
                              listing.status === 'AVAILABLE'
                                ? '#065F46'
                                : listing.status === 'RESERVED'
                                ? '#92400E'
                                : listing.status === 'COMPLETED'
                                ? '#3730A3'
                                : '#991B1B',
                          }}
                        >
                          {listing.status}
                        </span>
                      </td>
                      <td style={{ padding: '12px 16px', textAlign: 'right' }}>
                        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
                          {/* NGO Match Engine Button */}
                          <button
                            onClick={() => handleOpenMatches(listing)}
                            className="btn btn-secondary"
                            style={{ fontSize: '0.75rem', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: '4px' }}
                            title="Calculate AI NGO Matches"
                          >
                            <Award size={14} color="#D97706" />
                            <span>Matches</span>
                          </button>

                          {/* Review Claims Button */}
                          <button
                            onClick={() => handleOpenClaims(listing)}
                            className="btn btn-secondary"
                            style={{ fontSize: '0.75rem', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: '4px' }}
                            title="Review NGO Claims & Handover"
                          >
                            <Truck size={14} />
                            <span>Claims ({listing.claims_count})</span>
                          </button>

                          {/* Cancel Listing Button */}
                          {listing.status === 'AVAILABLE' && (
                            <button
                              onClick={() => handleCancelListing(listing.id)}
                              className="btn btn-secondary"
                              style={{ fontSize: '0.75rem', padding: '4px 8px', color: '#EF4444' }}
                              title="Cancel Listing & Release Stock"
                            >
                              <XCircle size={14} />
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ) : (
        /* NGO RESCUE MARKETPLACE VIEW */
        <div>
          {/* My Claims Tracker Section */}
          {myClaims.length > 0 && (
            <div className="card" style={{ padding: '16px', marginBottom: '24px', background: '#F8FAFC' }}>
              <div style={{ fontWeight: 600, color: 'var(--gray-900)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Truck size={18} color="var(--primary)" />
                <span>My Active Rescue Claims & Collections ({myClaims.length})</span>
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
                {myClaims.map((claim) => {
                  const sched = claim.pickup_schedule;
                  const isScheduled = !!sched;
                  const isReady = sched?.status === 'READY_FOR_COLLECTION' || claim.status === 'READY_FOR_PICKUP';
                  const isCollected = sched?.status === 'COLLECTED' || claim.status === 'PICKED_UP';
                  const isCompleted = sched?.status === 'COMPLETED' || claim.status === 'COMPLETED';

                  return (
                    <div
                      key={claim.id}
                      style={{
                        background: '#ffffff',
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        padding: '14px',
                        display: 'flex',
                        flexDirection: 'column',
                        justifyContent: 'space-between',
                      }}
                    >
                      <div>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                          <div style={{ fontWeight: 600, fontSize: '0.875rem' }}>{claim.listing_title}</div>
                          <span
                            style={{
                              fontSize: '0.6875rem',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              fontWeight: 700,
                              background:
                                claim.status === 'APPROVED' || claim.status === 'READY_FOR_PICKUP'
                                  ? '#D1FAE5'
                                  : claim.status === 'REQUESTED' || claim.status === 'PENDING'
                                  ? '#FEF3C7'
                                  : claim.status === 'PICKED_UP'
                                  ? '#DBEAFE'
                                  : claim.status === 'COMPLETED'
                                  ? '#E0E7FF'
                                  : '#FEE2E2',
                              color:
                                claim.status === 'APPROVED' || claim.status === 'READY_FOR_PICKUP'
                                  ? '#065F46'
                                  : claim.status === 'REQUESTED' || claim.status === 'PENDING'
                                  ? '#92400E'
                                  : claim.status === 'PICKED_UP'
                                  ? '#1E40AF'
                                  : claim.status === 'COMPLETED'
                                  ? '#3730A3'
                                  : '#991B1B',
                            }}
                          >
                            {claim.status}
                          </span>
                        </div>

                        <div style={{ fontSize: '0.8125rem', color: 'var(--gray-700)', marginTop: '4px' }}>
                          Claimed: <strong>{claim.claimed_quantity} {claim.unit}</strong>
                        </div>

                        {/* Milestone Tracker Mini Bar */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', margin: '8px 0', fontSize: '0.6875rem' }}>
                          <span style={{ color: isScheduled ? '#059669' : '#94A3B8', fontWeight: isScheduled ? 600 : 400, display: 'flex', alignItems: 'center', gap: '2px' }}>
                            <CheckCircle2 size={12} color={isScheduled ? '#059669' : '#94A3B8'} /> Sched
                          </span>
                          <span style={{ color: '#CBD5E1' }}>→</span>
                          <span style={{ color: isReady ? '#059669' : '#94A3B8', fontWeight: isReady ? 600 : 400, display: 'flex', alignItems: 'center', gap: '2px' }}>
                            <CheckCircle2 size={12} color={isReady ? '#059669' : '#94A3B8'} /> Ready
                          </span>
                          <span style={{ color: '#CBD5E1' }}>→</span>
                          <span style={{ color: isCollected ? '#059669' : '#94A3B8', fontWeight: isCollected ? 600 : 400, display: 'flex', alignItems: 'center', gap: '2px' }}>
                            <CheckCircle2 size={12} color={isCollected ? '#059669' : '#94A3B8'} /> Collected
                          </span>
                          <span style={{ color: '#CBD5E1' }}>→</span>
                          <span style={{ color: isCompleted ? '#059669' : '#94A3B8', fontWeight: isCompleted ? 600 : 400, display: 'flex', alignItems: 'center', gap: '2px' }}>
                            <CheckCircle2 size={12} color={isCompleted ? '#059669' : '#94A3B8'} /> Done
                          </span>
                        </div>

                        {/* Logistics Window details */}
                        {sched ? (
                          <div style={{ background: '#F1F5F9', padding: '6px 8px', borderRadius: '4px', marginTop: '6px', fontSize: '0.75rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '4px', color: 'var(--gray-800)', fontWeight: 500 }}>
                              <Calendar size={12} />
                              <span>{sched.pickup_date} ({new Date(sched.pickup_start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - {new Date(sched.pickup_end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })})</span>
                            </div>
                            {sched.driver_name && (
                              <div style={{ color: 'var(--gray-600)', marginTop: '2px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                                <Truck size={12} /> {sched.vehicle_type || 'Vehicle'} • {sched.driver_name} {sched.driver_phone ? `(${sched.driver_phone})` : ''}
                              </div>
                            )}
                            {sched.rescheduled_count > 0 && (
                              <div style={{ color: '#D97706', marginTop: '2px', fontSize: '0.6875rem' }}>
                                ↻ Rescheduled ({sched.rescheduled_count}x): {sched.rescheduled_reason}
                              </div>
                            )}
                          </div>
                        ) : claim.pickup_time ? (
                          <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '2px' }}>
                            Proposed: {new Date(claim.pickup_time).toLocaleString()}
                          </div>
                        ) : null}

                        {claim.rejection_reason && (
                          <div style={{ fontSize: '0.75rem', color: '#DC2626', marginTop: '4px' }}>
                            Reason: {claim.rejection_reason}
                          </div>
                        )}
                      </div>

                      {/* Action Triggers for NGO */}
                      <div style={{ marginTop: '10px', paddingTop: '8px', borderTop: '1px solid var(--border)', display: 'flex', flexWrap: 'wrap', gap: '6px', justifyContent: 'flex-end' }}>
                        {/* If approved or requested, NGO can schedule pickup */}
                        {!sched && (claim.status === 'APPROVED' || claim.status === 'REQUESTED' || claim.status === 'ACCEPTED') && (
                          <button
                            onClick={() => handleOpenSchedule(claim)}
                            className="btn btn-primary"
                            style={{ fontSize: '0.75rem', padding: '4px 8px', display: 'flex', alignItems: 'center', gap: '4px' }}
                          >
                            <Calendar size={12} /> Schedule Pickup
                          </button>
                        )}

                        {/* If scheduled, NGO can reschedule */}
                        {sched && sched.status !== 'COMPLETED' && sched.status !== 'CANCELLED' && (
                          <button
                            onClick={() => handleOpenReschedule(claim)}
                            className="btn btn-secondary"
                            style={{ fontSize: '0.75rem', padding: '4px 8px', display: 'flex', alignItems: 'center', gap: '4px' }}
                          >
                            <RefreshCw size={12} /> Reschedule
                          </button>
                        )}

                        {/* If ready for collection, NGO can confirm collected */}
                        {(sched?.status === 'READY_FOR_COLLECTION' || claim.status === 'READY_FOR_PICKUP') && (
                          <button
                            onClick={() => handleConfirmCollection(claim.id)}
                            className="btn btn-primary"
                            style={{ fontSize: '0.75rem', padding: '4px 8px', background: '#0284C7', display: 'flex', alignItems: 'center', gap: '4px' }}
                          >
                            <Truck size={12} /> Confirm Collected
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Marketplace Card Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '20px' }}>
            {listings
              .filter((l) => l.status === 'AVAILABLE' && l.remaining_claimable_quantity > 0)
              .map((listing) => (
                <div
                  key={listing.id}
                  className="card"
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    padding: '20px',
                    position: 'relative',
                    transition: 'transform 0.15s ease',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '8px' }}>
                    <span className="badge badge-secondary">{listing.category_name}</span>
                    <span
                      style={{
                        fontSize: '0.6875rem',
                        fontWeight: 700,
                        padding: '2px 8px',
                        borderRadius: '4px',
                        background: listing.storage_requirement === 'REFRIGERATED' ? '#DBEAFE' : '#F3F4F6',
                        color: listing.storage_requirement === 'REFRIGERATED' ? '#1E40AF' : '#374151',
                      }}
                    >
                      {listing.storage_requirement}
                    </span>
                  </div>

                  <h3 style={{ fontSize: '1.125rem', fontWeight: 700, color: 'var(--gray-900)', marginBottom: '4px' }}>
                    {listing.title || listing.product_name}
                  </h3>

                  <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', margin: '8px 0' }}>
                    <span style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--primary)' }}>
                      {listing.remaining_claimable_quantity}
                    </span>
                    <span style={{ fontSize: '0.875rem', color: 'var(--gray-600)' }}>{listing.unit} available</span>
                  </div>

                  {/* Urgency & Expiry */}
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '6px',
                      fontSize: '0.8125rem',
                      color: listing.days_to_expiry <= 1 ? '#EF4444' : 'var(--gray-600)',
                      marginBottom: '12px',
                    }}
                  >
                    <Clock size={16} />
                    <span>
                      {listing.days_to_expiry <= 0
                        ? 'Expires Today - Urgent Pickup!'
                        : `Expires in ${listing.days_to_expiry.toFixed(0)} days (${listing.expiry_date})`}
                    </span>
                  </div>

                  {/* Location */}
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: '6px', fontSize: '0.75rem', color: 'var(--gray-500)', marginBottom: '16px' }}>
                    <MapPin size={16} style={{ flexShrink: 0, marginTop: '2px' }} />
                    <span>{listing.pickup_address}</span>
                  </div>

                  {/* Claim Action */}
                  <div style={{ marginTop: 'auto', paddingTop: '12px', borderTop: '1px solid var(--border)' }}>
                    <button
                      onClick={() => {
                        setClaimingListing(listing);
                        setClaimQty(Math.min(25, listing.remaining_claimable_quantity));
                      }}
                      className="btn btn-primary"
                      style={{ width: '100%', justifyContent: 'center' }}
                    >
                      Claim This Food Donation
                    </button>
                  </div>
                </div>
              ))}
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* MODAL 1: EXPLAINABLE NGO MATCHING RECOMMENDATIONS */}
      {/* --------------------------------------------------------------------- */}
      {matchingListing && (
        <div className="modal-backdrop" style={{ zIndex: 100 }}>
          <div className="modal-dialog" style={{ maxWidth: '720px', width: '90%' }}>
            <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Award size={22} color="#D97706" />
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                  NGO Matches for "{matchingListing.title || matchingListing.product_name}"
                </h2>
              </div>
              <button
                onClick={() => setMatchingListing(null)}
                style={{ background: 'none', border: 'none', fontSize: '1.25rem', cursor: 'pointer' }}
              >
                ✕
              </button>
            </div>

            <div className="modal-body" style={{ maxHeight: '70vh', overflowY: 'auto', padding: '20px' }}>
              <div style={{ background: '#F8FAFC', padding: '12px 16px', borderRadius: '8px', marginBottom: '16px' }}>
                <div style={{ fontSize: '0.8125rem', color: 'var(--gray-600)' }}>
                  Batch Quantity: <strong>{matchingListing.quantity} {matchingListing.unit}</strong> • Storage: <strong>{matchingListing.storage_requirement}</strong> • Shelf Life: <strong>{matchingListing.days_to_expiry.toFixed(0)} days</strong>
                </div>
              </div>

              {loadingMatches ? (
                <div style={{ padding: '40px', textAlign: 'center', color: 'var(--gray-500)' }}>
                  Evaluating category, cold-chain storage, distance, and capacity algorithms...
                </div>
              ) : !matchResults || matchResults.matching_recommendations.length === 0 ? (
                <div style={{ padding: '30px', textAlign: 'center', color: 'var(--gray-500)' }}>
                  No compatible recipient NGOs found for this storage/category profile.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  {matchResults.matching_recommendations.map((rec, idx) => (
                    <div
                      key={rec.ngo_tenant_id}
                      style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        padding: '16px',
                        background: idx === 0 ? '#F0FDF4' : '#ffffff',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--gray-900)' }}>
                              {rec.ngo_name}
                            </span>
                            {rec.is_verified && (
                              <span
                                style={{
                                  fontSize: '0.6875rem',
                                  padding: '1px 6px',
                                  borderRadius: '9999px',
                                  background: '#D1FAE5',
                                  color: '#065F46',
                                  fontWeight: 600,
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: '2px',
                                }}
                              >
                                <ShieldCheck size={12} /> Verified
                              </span>
                            )}
                          </div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginTop: '2px' }}>
                            {rec.organization_type} • Max Capacity: {rec.max_capacity_units} units
                          </div>
                        </div>

                        {/* Match Score Badge */}
                        <div style={{ textAlign: 'right' }}>
                          <div
                            style={{
                              fontSize: '1.25rem',
                              fontWeight: 800,
                              color: rec.match_score >= 80 ? '#059669' : rec.match_score >= 60 ? '#D97706' : '#6B7280',
                            }}
                          >
                            {rec.match_score.toFixed(0)}%
                          </div>
                          <div style={{ fontSize: '0.6875rem', color: 'var(--gray-500)' }}>Fit Score</div>
                        </div>
                      </div>

                      {/* Transparent Match Reasons */}
                      <div style={{ marginTop: '10px', paddingTop: '10px', borderTop: '1px dashed var(--border)' }}>
                        <div style={{ fontSize: '0.6875rem', textTransform: 'uppercase', color: 'var(--gray-400)', fontWeight: 700, marginBottom: '4px' }}>
                          Explainable Match Factors:
                        </div>
                        <ul style={{ margin: 0, paddingLeft: '18px', fontSize: '0.75rem', color: 'var(--gray-700)' }}>
                          {rec.match_reasons.map((reason, rIdx) => (
                            <li key={rIdx} style={{ marginBottom: '2px' }}>
                              {reason}
                            </li>
                          ))}
                        </ul>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', padding: '16px 20px', borderTop: '1px solid var(--border)' }}>
              <button onClick={() => setMatchingListing(null)} className="btn btn-secondary">
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* MODAL 2: CLAIMS REVIEW & PHYSICAL DISPATCH (DONOR VIEW) */}
      {/* --------------------------------------------------------------------- */}
      {claimsListing && (
        <div className="modal-backdrop" style={{ zIndex: 100 }}>
          <div className="modal-dialog" style={{ maxWidth: '680px', width: '90%' }}>
            <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                Review Claims for "{claimsListing.title || claimsListing.product_name}"
              </h2>
              <button
                onClick={() => setClaimsListing(null)}
                style={{ background: 'none', border: 'none', fontSize: '1.25rem', cursor: 'pointer' }}
              >
                ✕
              </button>
            </div>

            <div className="modal-body" style={{ maxHeight: '70vh', overflowY: 'auto', padding: '20px' }}>
              {loadingClaims ? (
                <div style={{ padding: '30px', textAlign: 'center', color: 'var(--gray-500)' }}>
                  Loading claims...
                </div>
              ) : listingClaims.length === 0 ? (
                <div style={{ padding: '30px', textAlign: 'center', color: 'var(--gray-500)' }}>
                  No claims submitted for this listing yet.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
                  {listingClaims.map((claim) => (
                    <div
                      key={claim.id}
                      style={{
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        padding: '16px',
                        background: '#ffffff',
                      }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                        <div>
                          <div style={{ fontWeight: 700, fontSize: '0.9375rem', color: 'var(--gray-900)' }}>
                            {claim.ngo_name}
                          </div>
                          <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)' }}>
                            Claimed: <strong>{claim.claimed_quantity} {claim.unit}</strong> • Contact: {claim.claimed_by_user_name}
                          </div>
                          {claim.pickup_time && (
                            <div style={{ fontSize: '0.75rem', color: 'var(--gray-600)', marginTop: '2px' }}>
                              Requested Pickup: {new Date(claim.pickup_time).toLocaleString()}
                            </div>
                          )}
                          {claim.notes && (
                            <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', fontStyle: 'italic', marginTop: '2px' }}>
                              "{claim.notes}"
                            </div>
                          )}
                        </div>

                        <span
                          style={{
                            fontSize: '0.75rem',
                            padding: '2px 8px',
                            borderRadius: '4px',
                            fontWeight: 700,
                            background:
                              claim.status === 'APPROVED'
                                ? '#D1FAE5'
                                : claim.status === 'REQUESTED'
                                ? '#FEF3C7'
                                : claim.status === 'COMPLETED'
                                ? '#E0E7FF'
                                : '#FEE2E2',
                            color:
                              claim.status === 'APPROVED'
                                ? '#065F46'
                                : claim.status === 'REQUESTED'
                                ? '#92400E'
                                : claim.status === 'COMPLETED'
                                ? '#3730A3'
                                : '#991B1B',
                          }}
                        >
                          {claim.status}
                        </span>
                      </div>

                      {/* Logistics & Pickup Window Banner */}
                      {claim.pickup_schedule && (
                        <div style={{ background: '#F8FAFC', border: '1px solid #E2E8F0', padding: '10px 12px', borderRadius: '6px', marginTop: '10px', fontSize: '0.8125rem' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '4px' }}>
                            <span style={{ fontWeight: 600, color: 'var(--gray-900)', display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <Truck size={14} color="var(--primary)" />
                              Logistics Schedule: {claim.pickup_schedule.pickup_date}
                            </span>
                            <span style={{ fontSize: '0.6875rem', fontWeight: 700, padding: '2px 6px', borderRadius: '4px', background: '#E2E8F0', color: 'var(--gray-700)' }}>
                              {claim.pickup_schedule.status}
                            </span>
                          </div>
                          <div style={{ color: 'var(--gray-700)', fontSize: '0.75rem' }}>
                            Window: {new Date(claim.pickup_schedule.pickup_start_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} - {new Date(claim.pickup_schedule.pickup_end_time).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                          </div>
                          {claim.pickup_schedule.driver_name && (
                            <div style={{ color: 'var(--gray-600)', fontSize: '0.75rem', marginTop: '2px' }}>
                              Driver: {claim.pickup_schedule.driver_name} ({claim.pickup_schedule.driver_phone || 'No phone'}) • {claim.pickup_schedule.vehicle_type || 'Vehicle'}
                            </div>
                          )}
                          {claim.pickup_schedule.rescheduled_count > 0 && (
                            <div style={{ color: '#D97706', fontSize: '0.75rem', marginTop: '2px' }}>
                              ↻ Rescheduled ({claim.pickup_schedule.rescheduled_count}x): {claim.pickup_schedule.rescheduled_reason}
                            </div>
                          )}
                          {claim.pickup_schedule.cancellation_reason && (
                            <div style={{ color: '#DC2626', fontSize: '0.75rem', marginTop: '2px' }}>
                              Alert: {claim.pickup_schedule.cancellation_reason}
                            </div>
                          )}
                        </div>
                      )}

                      {/* Action Triggers */}
                      <div style={{ marginTop: '12px', paddingTop: '10px', borderTop: '1px solid var(--border)', display: 'flex', flexWrap: 'wrap', justifyContent: 'flex-end', gap: '8px' }}>
                        {claim.status === 'REQUESTED' && (
                          <>
                            <button
                              onClick={() => handleReviewClaim(claim.id, 'APPROVE')}
                              className="btn btn-primary"
                              style={{ fontSize: '0.75rem', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: '4px' }}
                            >
                              <Check size={14} /> Approve Reservation
                            </button>
                            <button
                              onClick={() => setRejectingClaimId(claim.id)}
                              className="btn btn-secondary"
                              style={{ fontSize: '0.75rem', padding: '4px 10px', color: '#EF4444' }}
                            >
                              Decline
                            </button>
                          </>
                        )}

                        {/* If approved without schedule, donor can propose window */}
                        {!claim.pickup_schedule && (claim.status === 'APPROVED' || claim.status === 'ACCEPTED') && (
                          <button
                            onClick={() => handleOpenSchedule(claim)}
                            className="btn btn-secondary"
                            style={{ fontSize: '0.75rem', padding: '4px 10px', display: 'flex', alignItems: 'center', gap: '4px' }}
                          >
                            <Calendar size={14} /> Schedule Pickup Window
                          </button>
                        )}

                        {/* If schedule exists and is scheduled/rescheduled, donor can mark ready or missed */}
                        {claim.pickup_schedule && (claim.pickup_schedule.status === 'SCHEDULED' || claim.pickup_schedule.status === 'RESCHEDULED') && (
                          <>
                            <button
                              onClick={() => handleMarkReady(claim.id)}
                              className="btn btn-primary"
                              style={{ fontSize: '0.75rem', padding: '4px 10px', background: '#0284C7', display: 'flex', alignItems: 'center', gap: '4px' }}
                            >
                              <Package size={14} /> Mark Ready for Collection
                            </button>
                            <button
                              onClick={() => handleMarkMissed(claim.id)}
                              className="btn btn-secondary"
                              style={{ fontSize: '0.75rem', padding: '4px 10px', color: '#DC2626' }}
                            >
                              Flag Missed
                            </button>
                          </>
                        )}

                        {/* Handover confirmation button */}
                        {(claim.status === 'APPROVED' || claim.status === 'READY_FOR_PICKUP' || claim.status === 'PICKED_UP' || claim.pickup_schedule?.status === 'READY_FOR_COLLECTION' || claim.pickup_schedule?.status === 'COLLECTED') && claim.status !== 'COMPLETED' && (
                          <button
                            onClick={() => handleCompleteHandover(claim.id)}
                            className="btn btn-primary"
                            style={{ fontSize: '0.75rem', padding: '6px 12px', background: '#059669', display: 'flex', alignItems: 'center', gap: '6px' }}
                          >
                            <Truck size={14} />
                            <span>Confirm Handover & Deduct Stock</span>
                          </button>
                        )}
                      </div>

                      {/* Rejection input box */}
                      {rejectingClaimId === claim.id && (
                        <div style={{ marginTop: '10px', background: '#FEF2F2', padding: '8px', borderRadius: '6px' }}>
                          <input
                            type="text"
                            placeholder="Reason for declining..."
                            value={rejectionReason}
                            onChange={(e) => setRejectionReason(e.target.value)}
                            className="form-input"
                            style={{ fontSize: '0.75rem', marginBottom: '6px' }}
                          />
                          <div style={{ display: 'flex', gap: '6px', justifyContent: 'flex-end' }}>
                            <button
                              onClick={() => setRejectingClaimId(null)}
                              className="btn btn-secondary"
                              style={{ fontSize: '0.75rem', padding: '2px 8px' }}
                            >
                              Cancel
                            </button>
                            <button
                              onClick={() => handleReviewClaim(claim.id, 'REJECT')}
                              className="btn btn-primary"
                              style={{ fontSize: '0.75rem', padding: '2px 8px', background: '#DC2626' }}
                            >
                              Confirm Rejection
                            </button>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', padding: '16px 20px', borderTop: '1px solid var(--border)' }}>
              <button onClick={() => setClaimsListing(null)} className="btn btn-secondary">
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* MODAL 3: NGO CLAIM SUBMISSION FORM */}
      {/* --------------------------------------------------------------------- */}
      {claimingListing && (
        <div className="modal-backdrop" style={{ zIndex: 100 }}>
          <div className="modal-dialog" style={{ maxWidth: '520px', width: '90%' }}>
            <form onSubmit={handleSubmitClaim}>
              <div className="modal-header">
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                  Claim Food Donation
                </h2>
              </div>
              <div className="modal-body" style={{ padding: '20px' }}>
                <div style={{ background: '#F8FAFC', padding: '12px', borderRadius: '6px', marginBottom: '16px' }}>
                  <div style={{ fontWeight: 600 }}>{claimingListing.title || claimingListing.product_name}</div>
                  <div style={{ fontSize: '0.8125rem', color: 'var(--gray-600)', marginTop: '2px' }}>
                    Max claimable: <strong>{claimingListing.remaining_claimable_quantity} {claimingListing.unit}</strong>
                  </div>
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label className="form-label">Quantity to Rescue ({claimingListing.unit}) *</label>
                  <input
                    type="number"
                    min="1"
                    max={claimingListing.remaining_claimable_quantity}
                    step="0.5"
                    value={claimQty}
                    onChange={(e) => setClaimQty(parseFloat(e.target.value) || 0)}
                    className="form-input"
                    required
                  />
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label className="form-label">Estimated Collection Time</label>
                  <input
                    type="datetime-local"
                    value={claimPickupTime}
                    onChange={(e) => setClaimPickupTime(e.target.value)}
                    className="form-input"
                  />
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label className="form-label">Notes for Food Business Donor</label>
                  <textarea
                    rows={2}
                    placeholder="e.g. Bringing refrigerated van; distributing to homeless shelter tonight."
                    value={claimNotes}
                    onChange={(e) => setClaimNotes(e.target.value)}
                    className="form-input"
                  />
                </div>
              </div>
              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', padding: '16px 20px', borderTop: '1px solid var(--border)' }}>
                <button type="button" onClick={() => setClaimingListing(null)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={submittingClaim} className="btn btn-primary">
                  {submittingClaim ? 'Submitting...' : 'Submit Claim Request'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* MODAL 4: CREATE SURPLUS LISTING (DONOR VIEW) */}
      {/* --------------------------------------------------------------------- */}
      {showCreateModal && (
        <div className="modal-backdrop" style={{ zIndex: 100 }}>
          <div className="modal-dialog" style={{ maxWidth: '600px', width: '90%' }}>
            <form onSubmit={handleCreateListing}>
              <div className="modal-header">
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                  Create Surplus Food Listing
                </h2>
              </div>
              <div className="modal-body" style={{ padding: '20px' }}>
                {createError && (
                  <div style={{ background: '#FEF2F2', color: '#991B1B', padding: '10px 14px', borderRadius: '6px', fontSize: '0.8125rem', marginBottom: '16px' }}>
                    {createError}
                  </div>
                )}

                <div style={{ marginBottom: '16px' }}>
                  <label className="form-label">Select Inventory Item *</label>
                  <select
                    value={selectedItemId}
                    onChange={(e) => {
                      setSelectedItemId(e.target.value);
                      const item = inventoryItems.find((i) => i.id === e.target.value);
                      if (item) {
                        setListingTitle(`Surplus ${item.name}`);
                        setListingQty(Math.min(10, item.current_quantity));
                      }
                    }}
                    className="form-select"
                    required
                  >
                    <option value="">-- Choose inventory item --</option>
                    {inventoryItems.map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.name} ({item.current_quantity} {item.unit} on hand • Expires: {item.expiry_date})
                      </option>
                    ))}
                  </select>
                </div>

                {selectedItemData && (
                  <div style={{ background: '#F8FAFC', padding: '10px 14px', borderRadius: '6px', fontSize: '0.8125rem', marginBottom: '16px' }}>
                    Available On-Hand: <strong>{selectedItemData.current_quantity} {selectedItemData.unit}</strong> • Storage: <strong>{selectedItemData.storage_requirement}</strong> • Expiry: <strong>{selectedItemData.expiry_date}</strong>
                  </div>
                )}

                <div style={{ marginBottom: '16px' }}>
                  <label className="form-label">Listing Title</label>
                  <input
                    type="text"
                    value={listingTitle}
                    onChange={(e) => setListingTitle(e.target.value)}
                    className="form-input"
                    placeholder="e.g. Fresh Bakery Loaves & Pastries"
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                  <div>
                    <label className="form-label">Quantity to Earmark *</label>
                    <input
                      type="number"
                      min="0.5"
                      step="0.5"
                      value={listingQty}
                      onChange={(e) => setListingQty(parseFloat(e.target.value) || 0)}
                      className="form-input"
                      required
                    />
                  </div>
                  <div>
                    <label className="form-label">Available Until *</label>
                    <input
                      type="datetime-local"
                      value={availableUntil}
                      onChange={(e) => setAvailableUntil(e.target.value)}
                      className="form-input"
                      required
                    />
                  </div>
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label className="form-label">Pickup Address *</label>
                  <input
                    type="text"
                    value={pickupAddress}
                    onChange={(e) => setPickupAddress(e.target.value)}
                    className="form-input"
                    required
                  />
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label className="form-label">Pickup Instructions</label>
                  <textarea
                    rows={2}
                    value={pickupInstructions}
                    onChange={(e) => setPickupInstructions(e.target.value)}
                    className="form-input"
                  />
                </div>
              </div>

              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', padding: '16px 20px', borderTop: '1px solid var(--border)' }}>
                <button type="button" onClick={() => setShowCreateModal(false)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={creatingListing} className="btn btn-primary">
                  {creatingListing ? 'Creating...' : 'Earmark & Publish Surplus'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* MODAL 5: NGO OPERATIONAL CAPABILITIES PROFILE */}
      {/* --------------------------------------------------------------------- */}
      {showProfileModal && ngoProfile && (
        <div className="modal-backdrop" style={{ zIndex: 100 }}>
          <div className="modal-dialog" style={{ maxWidth: '640px', width: '90%' }}>
            <form onSubmit={handleSaveNgoProfile}>
              <div className="modal-header">
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700 }}>
                  NGO Operational Rescue Capabilities
                </h2>
              </div>
              <div className="modal-body" style={{ maxHeight: '70vh', overflowY: 'auto', padding: '20px' }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                  <div>
                    <label className="form-label">Contact Person</label>
                    <input
                      type="text"
                      value={ngoProfile.contact_person}
                      onChange={(e) => setNgoProfile({ ...ngoProfile, contact_person: e.target.value })}
                      className="form-input"
                      required
                    />
                  </div>
                  <div>
                    <label className="form-label">Contact Phone</label>
                    <input
                      type="text"
                      value={ngoProfile.contact_phone}
                      onChange={(e) => setNgoProfile({ ...ngoProfile, contact_phone: e.target.value })}
                      className="form-input"
                      required
                    />
                  </div>
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label className="form-label">Operating Address</label>
                  <input
                    type="text"
                    value={ngoProfile.address}
                    onChange={(e) => setNgoProfile({ ...ngoProfile, address: e.target.value })}
                    className="form-input"
                    required
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                  <div>
                    <label className="form-label">Max Single Batch Capacity (units)</label>
                    <input
                      type="number"
                      value={ngoProfile.max_capacity_units}
                      onChange={(e) => setNgoProfile({ ...ngoProfile, max_capacity_units: parseFloat(e.target.value) || 0 })}
                      className="form-input"
                      required
                    />
                  </div>
                  <div>
                    <label className="form-label">Service Radius (km)</label>
                    <input
                      type="number"
                      value={ngoProfile.service_radius_km}
                      onChange={(e) => setNgoProfile({ ...ngoProfile, service_radius_km: parseFloat(e.target.value) || 0 })}
                      className="form-input"
                      required
                    />
                  </div>
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label className="form-label">Storage Capabilities (Cold-Chain)</label>
                  <div style={{ display: 'flex', gap: '12px', marginTop: '6px' }}>
                    {['AMBIENT', 'REFRIGERATED', 'FROZEN'].map((fac) => {
                      const isChecked = ngoProfile.storage_facilities.includes(fac);
                      return (
                        <label key={fac} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '0.8125rem' }}>
                          <input
                            type="checkbox"
                            checked={isChecked}
                            onChange={(e) => {
                              const next = e.target.checked
                                ? [...ngoProfile.storage_facilities, fac]
                                : ngoProfile.storage_facilities.filter((f) => f !== fac);
                              setNgoProfile({ ...ngoProfile, storage_facilities: next });
                            }}
                          />
                          <span>{fac}</span>
                        </label>
                      );
                    })}
                  </div>
                </div>

                <div style={{ marginBottom: '16px' }}>
                  <label className="form-label">Accepted Food Categories</label>
                  <div style={{ fontSize: '0.75rem', color: 'var(--gray-500)', marginBottom: '6px' }}>
                    Current: {ngoProfile.accepted_categories.join(', ')}
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {['ALL', 'Bakery', 'Dairy', 'Produce', 'Meat', 'Pantry'].map((cat) => {
                      const active = ngoProfile.accepted_categories.includes(cat);
                      return (
                        <button
                          key={cat}
                          type="button"
                          onClick={() => {
                            let next: string[];
                            if (cat === 'ALL') {
                              next = ['ALL'];
                            } else {
                              const withoutAll = ngoProfile.accepted_categories.filter((c) => c !== 'ALL');
                              next = active ? withoutAll.filter((c) => c !== cat) : [...withoutAll, cat];
                              if (next.length === 0) next = ['ALL'];
                            }
                            setNgoProfile({ ...ngoProfile, accepted_categories: next });
                          }}
                          className={`btn ${active ? 'btn-primary' : 'btn-secondary'}`}
                          style={{ fontSize: '0.75rem', padding: '4px 10px' }}
                        >
                          {cat}
                        </button>
                      );
                    })}
                  </div>
                </div>
              </div>

              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', padding: '16px 20px', borderTop: '1px solid var(--border)' }}>
                <button type="button" onClick={() => setShowProfileModal(false)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={profileSaving} className="btn btn-primary">
                  {profileSaving ? 'Saving...' : 'Save Profile Capabilities'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* MODAL 6: SCHEDULE PICKUP LOGISTICS (Phase 2) */}
      {/* --------------------------------------------------------------------- */}
      {schedulingClaim && (
        <div className="modal-backdrop" style={{ zIndex: 110 }}>
          <div className="modal-dialog" style={{ maxWidth: '580px', width: '90%' }}>
            <form onSubmit={handleSaveSchedule}>
              <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <Calendar size={20} color="var(--primary)" />
                  Schedule Pickup Logistics
                </h2>
                <button
                  type="button"
                  onClick={() => setSchedulingClaim(null)}
                  style={{ background: 'none', border: 'none', fontSize: '1.25rem', cursor: 'pointer' }}
                >
                  ✕
                </button>
              </div>

              <div className="modal-body" style={{ maxHeight: '70vh', overflowY: 'auto', padding: '20px' }}>
                <div style={{ background: '#F8FAFC', padding: '10px 14px', borderRadius: '6px', marginBottom: '16px', fontSize: '0.8125rem' }}>
                  Rescuing: <strong>{schedulingClaim.claimed_quantity} {schedulingClaim.unit}</strong> of <em>{schedulingClaim.listing_title}</em>
                </div>

                <div style={{ marginBottom: '14px' }}>
                  <label className="form-label">Pickup Date *</label>
                  <input
                    type="date"
                    value={schedDate}
                    onChange={(e) => setSchedDate(e.target.value)}
                    className="form-input"
                    required
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                  <div>
                    <label className="form-label">Window Start *</label>
                    <input
                      type="datetime-local"
                      value={schedStartTime}
                      onChange={(e) => setSchedStartTime(e.target.value)}
                      className="form-input"
                      required
                    />
                  </div>
                  <div>
                    <label className="form-label">Window End *</label>
                    <input
                      type="datetime-local"
                      value={schedEndTime}
                      onChange={(e) => setSchedEndTime(e.target.value)}
                      className="form-input"
                      required
                    />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                  <div>
                    <label className="form-label">Vehicle Type</label>
                    <select
                      value={schedVehicleType}
                      onChange={(e) => setSchedVehicleType(e.target.value)}
                      className="form-select"
                    >
                      <option value="VAN">Cargo Van</option>
                      <option value="REFRIGERATED_TRUCK">Refrigerated Truck (Cold-Chain)</option>
                      <option value="CAR">Personal Car / Hatchback</option>
                      <option value="CARGO_BIKE">Cargo Bike / Courier</option>
                      <option value="OTHER">Other Logistics</option>
                    </select>
                  </div>
                  <div>
                    <label className="form-label">Driver / Volunteer Name</label>
                    <input
                      type="text"
                      placeholder="e.g. Alex Volunteer"
                      value={schedDriverName}
                      onChange={(e) => setSchedDriverName(e.target.value)}
                      className="form-input"
                    />
                  </div>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                  <div>
                    <label className="form-label">Driver Phone</label>
                    <input
                      type="tel"
                      placeholder="+1-555-0100"
                      value={schedDriverPhone}
                      onChange={(e) => setSchedDriverPhone(e.target.value)}
                      className="form-input"
                    />
                  </div>
                  <div>
                    <label className="form-label">Pickup Location</label>
                    <input
                      type="text"
                      value={schedLocation}
                      onChange={(e) => setSchedLocation(e.target.value)}
                      className="form-input"
                      required
                    />
                  </div>
                </div>

                <div style={{ marginBottom: '14px' }}>
                  <label className="form-label">Special Handling / Instructions</label>
                  <textarea
                    rows={2}
                    placeholder="e.g. ring back dock bell, bring coolers"
                    value={schedInstructions}
                    onChange={(e) => setSchedInstructions(e.target.value)}
                    className="form-input"
                  />
                </div>
              </div>

              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', padding: '16px 20px', borderTop: '1px solid var(--border)' }}>
                <button type="button" onClick={() => setSchedulingClaim(null)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={scheduleLoading} className="btn btn-primary">
                  {scheduleLoading ? 'Confirming...' : 'Lock Pickup Window'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* --------------------------------------------------------------------- */}
      {/* MODAL 7: RESCHEDULE PICKUP (Phase 2) */}
      {/* --------------------------------------------------------------------- */}
      {reschedulingClaim && (
        <div className="modal-backdrop" style={{ zIndex: 110 }}>
          <div className="modal-dialog" style={{ maxWidth: '540px', width: '90%' }}>
            <form onSubmit={handleSaveReschedule}>
              <div className="modal-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <h2 style={{ fontSize: '1.25rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <RefreshCw size={20} color="var(--primary)" />
                  Reschedule Pickup Window
                </h2>
                <button
                  type="button"
                  onClick={() => setReschedulingClaim(null)}
                  style={{ background: 'none', border: 'none', fontSize: '1.25rem', cursor: 'pointer' }}
                >
                  ✕
                </button>
              </div>

              <div className="modal-body" style={{ maxHeight: '70vh', overflowY: 'auto', padding: '20px' }}>
                <div style={{ marginBottom: '14px' }}>
                  <label className="form-label">New Pickup Date *</label>
                  <input
                    type="date"
                    value={schedDate}
                    onChange={(e) => setSchedDate(e.target.value)}
                    className="form-input"
                    required
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                  <div>
                    <label className="form-label">New Window Start *</label>
                    <input
                      type="datetime-local"
                      value={schedStartTime}
                      onChange={(e) => setSchedStartTime(e.target.value)}
                      className="form-input"
                      required
                    />
                  </div>
                  <div>
                    <label className="form-label">New Window End *</label>
                    <input
                      type="datetime-local"
                      value={schedEndTime}
                      onChange={(e) => setSchedEndTime(e.target.value)}
                      className="form-input"
                      required
                    />
                  </div>
                </div>

                <div style={{ marginBottom: '14px' }}>
                  <label className="form-label">Reason for Rescheduling *</label>
                  <input
                    type="text"
                    placeholder="e.g. Vehicle delay, volunteer schedule adjustment"
                    value={reschedReason}
                    onChange={(e) => setReschedReason(e.target.value)}
                    className="form-input"
                    required
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px', marginBottom: '14px' }}>
                  <div>
                    <label className="form-label">Driver Name</label>
                    <input
                      type="text"
                      value={schedDriverName}
                      onChange={(e) => setSchedDriverName(e.target.value)}
                      className="form-input"
                    />
                  </div>
                  <div>
                    <label className="form-label">Driver Phone</label>
                    <input
                      type="tel"
                      value={schedDriverPhone}
                      onChange={(e) => setSchedDriverPhone(e.target.value)}
                      className="form-input"
                    />
                  </div>
                </div>
              </div>

              <div className="modal-footer" style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px', padding: '16px 20px', borderTop: '1px solid var(--border)' }}>
                <button type="button" onClick={() => setReschedulingClaim(null)} className="btn btn-secondary">
                  Cancel
                </button>
                <button type="submit" disabled={scheduleLoading} className="btn btn-primary">
                  {scheduleLoading ? 'Updating...' : 'Update & Notify Counterpart'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
