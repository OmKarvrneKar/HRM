import React, { useState, useEffect } from 'react';
import { Laptop, KeyRound, Building2, MapPin, CheckCircle, AlertTriangle, ShieldCheck, X, PlusCircle, Trash2 } from 'lucide-react';
import { enterpriseApi } from '../../services/api/enterpriseApi';
import { adminApi } from '../../services/api/adminApi';
import { useAuth } from '../../hooks/useAuth';
import StatCard from '../../components/common/StatCard';
import Badge from '../../components/common/Badge';

export const AssetsInventory = () => {
  const { user } = useAuth();
  const userRole = (user?.role || '').toLowerCase();
  const canManageFacilities = ['admin', 'hr', 'hr_manager'].includes(userRole);

  const [activeTab, setActiveTab] = useState('hardware'); // 'hardware', 'software', 'rooms', 'seating'
  const [hardware, setHardware] = useState([]);
  const [software, setSoftware] = useState([]);
  const [rooms, setRooms] = useState([]);
  const [seating, setSeating] = useState([]);
  const [directoryUsers, setDirectoryUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [actionMsg, setActionMsg] = useState(null);

  // Modal State for Room Creation / Verification
  const [isRoomModalOpen, setIsRoomModalOpen] = useState(false);
  const [selectedRoom, setSelectedRoom] = useState(null); // null => create new verified room
  const [verifyRoomName, setVerifyRoomName] = useState('');
  const [verifyRoomFloor, setVerifyRoomFloor] = useState('');
  const [verifyRoomCapacity, setVerifyRoomCapacity] = useState('');
  const [verifyRoomFeatures, setVerifyRoomFeatures] = useState('');
  const [verifyRoomNotes, setVerifyRoomNotes] = useState('');

  // Modal State for Seating Creation / Verification
  const [isSeatingModalOpen, setIsSeatingModalOpen] = useState(false);
  const [selectedSeating, setSelectedSeating] = useState(null); // null => allocate new verified workstation
  const [targetEmployeeId, setTargetEmployeeId] = useState('');
  const [verifyFloor, setVerifyFloor] = useState('');
  const [verifyDesk, setVerifyDesk] = useState('');
  const [verifyLocker, setVerifyLocker] = useState('');
  const [verifyBay, setVerifyBay] = useState('');
  const [verifySeatingNotes, setVerifySeatingNotes] = useState('');

  const fetchAssets = async () => {
    try {
      setLoading(true);
      const calls = [
        enterpriseApi.getAssetsInventory(),
        enterpriseApi.getMeetingRooms(),
        enterpriseApi.getSeatingAllocations(),
      ];
      if (canManageFacilities) {
        calls.push(adminApi.getUsers());
      }
      const [invRes, rmRes, seatRes, usersRes] = await Promise.allSettled(calls);

      if (invRes.status === 'fulfilled') {
        const inv = invRes.value || {};
        setHardware((inv.hardware || []).filter((h) => Boolean(h?.is_verified)));
        setSoftware((inv.software || []).filter((s) => Boolean(s?.is_verified)));
      }
      if (rmRes.status === 'fulfilled') {
        const rawRooms = Array.isArray(rmRes.value?.rooms)
          ? rmRes.value.rooms
          : (Array.isArray(rmRes.value) ? rmRes.value : []);
        setRooms(rawRooms.filter((r) => Boolean(r?.is_verified)));
      }
      if (seatRes.status === 'fulfilled') {
        const seatData = seatRes.value || {};
        const allocList = (seatData.all_allocations || seatData.allocations || []).filter((s) =>
          Boolean(s?.is_verified)
        );
        if (allocList.length === 0 && seatData.my_seating?.is_verified) {
          setSeating([seatData.my_seating]);
        } else {
          setSeating(allocList);
        }
      }
      if (usersRes && usersRes.status === 'fulfilled') {
        setDirectoryUsers(usersRes.value?.users || []);
      }
    } catch (e) {
      console.warn('Assets fetch notice:', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAssets();
  }, [canManageFacilities]);

  // Room creation & verification handlers
  const handleOpenCreateRoomModal = () => {
    setSelectedRoom(null);
    setVerifyRoomName('');
    setVerifyRoomFloor('');
    setVerifyRoomCapacity('');
    setVerifyRoomFeatures('');
    setVerifyRoomNotes('');
    setIsRoomModalOpen(true);
  };

  const handleOpenVerifyRoomModal = (room) => {
    setSelectedRoom(room);
    setVerifyRoomName(room.name || '');
    setVerifyRoomFloor(room.floor || '');
    setVerifyRoomCapacity(room.capacity || '');
    setVerifyRoomFeatures(Array.isArray(room.features) ? room.features.join(', ') : '');
    setVerifyRoomNotes('');
    setIsRoomModalOpen(true);
  };

  const handleSubmitVerifyRoom = async (e) => {
    e.preventDefault();
    if (!verifyRoomNotes.trim()) {
      alert('Physical verification audit notes are required to certify this facility room.');
      return;
    }
    const parsedCap = parseInt(verifyRoomCapacity, 10);
    if (!verifyRoomName.trim() || !verifyRoomFloor.trim() || !parsedCap || parsedCap <= 0) {
      alert('Please provide confirmed room name, physical floor, and positive seat capacity.');
      return;
    }
    const payload = {
      name: verifyRoomName.trim(),
      floor: verifyRoomFloor.trim(),
      capacity: parsedCap,
      features: verifyRoomFeatures.split(',').map((f) => f.trim()).filter(Boolean),
      notes: verifyRoomNotes.trim(),
    };
    try {
      if (selectedRoom) {
        await enterpriseApi.verifyMeetingRoom(selectedRoom.room_id, payload);
        setActionMsg(`Meeting room ${selectedRoom.room_id} formally verified.`);
      } else {
        await enterpriseApi.createMeetingRoom(payload);
        setActionMsg(`Verified meeting room "${payload.name}" registered.`);
      }
      setIsRoomModalOpen(false);
      await fetchAssets();
      setTimeout(() => setActionMsg(null), 3000);
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to save verified meeting room.');
    }
  };

  const handleDeleteRoom = async (roomId, roomName) => {
    if (!window.confirm(`Remove meeting room "${roomName || roomId}"?`)) return;
    try {
      await enterpriseApi.deleteMeetingRoom(roomId);
      setActionMsg(`Meeting room ${roomId} removed.`);
      await fetchAssets();
      setTimeout(() => setActionMsg(null), 3000);
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to delete meeting room.');
    }
  };

  // Seating creation & verification handlers
  const handleOpenCreateSeatingModal = () => {
    setSelectedSeating(null);
    setTargetEmployeeId('');
    setVerifyFloor('');
    setVerifyBay('');
    setVerifyDesk('');
    setVerifyLocker('');
    setVerifySeatingNotes('');
    setIsSeatingModalOpen(true);
  };

  const handleOpenVerifySeatingModal = (alloc) => {
    setSelectedSeating(alloc);
    setTargetEmployeeId(alloc.employee_id || '');
    setVerifyFloor(alloc.floor || '');
    setVerifyDesk(alloc.desk_number || alloc.desk || '');
    setVerifyLocker(alloc.locker_number || alloc.locker || '');
    setVerifyBay(alloc.bay || '');
    setVerifySeatingNotes('');
    setIsSeatingModalOpen(true);
  };

  const handleSubmitVerifySeating = async (e) => {
    e.preventDefault();
    if (!verifySeatingNotes.trim()) {
      alert('Physical verification audit notes are required to certify this workstation allocation.');
      return;
    }
    if (!verifyFloor.trim() || !verifyDesk.trim() || !verifyBay.trim()) {
      alert('Please provide confirmed physical floor, zone/bay, and official desk identifier.');
      return;
    }
    try {
      if (selectedSeating) {
        await enterpriseApi.verifySeatingAllocation(selectedSeating.allocation_id, {
          floor: verifyFloor.trim(),
          desk_number: verifyDesk.trim().toUpperCase(),
          locker_number: verifyLocker.trim().toUpperCase(),
          bay: verifyBay.trim(),
          notes: verifySeatingNotes.trim(),
        });
        setActionMsg(`Workstation allocation ${selectedSeating.allocation_id} formally verified.`);
      } else {
        if (!targetEmployeeId.trim()) {
          alert('Please select or enter an Employee ID.');
          return;
        }
        await enterpriseApi.allocateSeating({
          employee_id: targetEmployeeId.trim().toUpperCase(),
          floor: verifyFloor.trim(),
          bay: verifyBay.trim(),
          desk_number: verifyDesk.trim().toUpperCase(),
          locker_number: verifyLocker.trim().toUpperCase(),
          notes: verifySeatingNotes.trim(),
        });
        setActionMsg(`Verified workstation assigned to ${targetEmployeeId.trim().toUpperCase()}.`);
      }
      setIsSeatingModalOpen(false);
      await fetchAssets();
      setTimeout(() => setActionMsg(null), 3000);
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to save workstation allocation.');
    }
  };

  const verifiedHardware = hardware.filter((h) => Boolean(h?.is_verified));
  const verifiedSoftware = software.filter((s) => Boolean(s?.is_verified));
  const verifiedRooms = rooms.filter((r) => Boolean(r?.is_verified));
  const confirmedSeating = seating.filter((s) => Boolean(s?.is_verified));

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Enterprise Assets, IT & Facilities
          </h1>
          <p className="text-xs text-slate-500 mt-1">
            Governance of verified company hardware, software seats, physical facility rooms, and desk bays.
          </p>
        </div>
        {actionMsg && (
          <div className="px-3.5 py-1.5 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs font-semibold flex items-center gap-2">
            <CheckCircle className="w-4 h-4 text-emerald-600" />
            {actionMsg}
          </div>
        )}
      </div>

      {/* KPI Cards: Strictly Verified Company Records */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <StatCard
          title="Hardware Devices"
          value={`${verifiedHardware.length} Confirmed`}
          subtitle="Administrator-verified only"
          icon={Laptop}
          color={verifiedHardware.length > 0 ? 'blue' : 'slate'}
        />
        <StatCard
          title="Software Seats"
          value={`${verifiedSoftware.length} Confirmed`}
          subtitle="Administrator-verified only"
          icon={KeyRound}
          color={verifiedSoftware.length > 0 ? 'purple' : 'slate'}
        />
        <StatCard
          title="Verified Meeting Rooms"
          value={`${verifiedRooms.length} Confirmed`}
          subtitle="Administrator-verified only"
          icon={Building2}
          color={verifiedRooms.length > 0 ? 'green' : 'slate'}
        />
        <StatCard
          title="Confirmed Desks"
          value={`${confirmedSeating.length} Allocated`}
          subtitle="Administrator-verified only"
          icon={MapPin}
          color={confirmedSeating.length > 0 ? 'amber' : 'slate'}
        />
      </div>

      {/* Corporate Facility Governance Notice */}
      <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-start gap-2.5">
        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
        <div>
          <span className="font-bold">Official Governance Notice:</span> Facility meeting rooms and employee workstation or locker assignments appear here only when formally entered and physically verified by HR or System Administration with audit evidence.
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-200">
        <button
          onClick={() => setActiveTab('hardware')}
          className={`py-3 px-4 text-xs font-semibold uppercase tracking-wider transition ${
            activeTab === 'hardware'
              ? 'border-b-2 border-blue-600 text-blue-700 bg-blue-50/40'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          Hardware Inventory
        </button>
        <button
          onClick={() => setActiveTab('software')}
          className={`py-3 px-4 text-xs font-semibold uppercase tracking-wider transition ${
            activeTab === 'software'
              ? 'border-b-2 border-blue-600 text-blue-700 bg-blue-50/40'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          Software Licenses
        </button>
        <button
          onClick={() => setActiveTab('rooms')}
          className={`py-3 px-4 text-xs font-semibold uppercase tracking-wider transition ${
            activeTab === 'rooms'
              ? 'border-b-2 border-blue-600 text-blue-700 bg-blue-50/40'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          Meeting Rooms ({verifiedRooms.length} Verified)
        </button>
        <button
          onClick={() => setActiveTab('seating')}
          className={`py-3 px-4 text-xs font-semibold uppercase tracking-wider transition ${
            activeTab === 'seating'
              ? 'border-b-2 border-blue-600 text-blue-700 bg-blue-50/40'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          Desk & Locker Bay ({confirmedSeating.length} Confirmed)
        </button>
      </div>

      {/* Tab: Hardware */}
      {activeTab === 'hardware' && (
        <div className="card">
          <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
            <Laptop className="w-4 h-4 text-blue-600" />
            Hardware Asset Registry
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                <tr>
                  <th className="p-3">Asset Tag</th>
                  <th className="p-3">Device Model</th>
                  <th className="p-3">Category</th>
                  <th className="p-3">Serial No</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Verification</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {verifiedHardware.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-4 text-center text-slate-500">
                      No verified hardware assets registered.
                    </td>
                  </tr>
                ) : (
                  verifiedHardware.map((h, i) => (
                    <tr key={i} className="hover:bg-slate-50/60">
                      <td className="p-3 font-mono font-bold text-blue-700">{h.asset_tag}</td>
                      <td className="p-3 font-semibold text-slate-800">{h.model}</td>
                      <td className="p-3 text-slate-600">{h.type}</td>
                      <td className="p-3 font-mono text-slate-500">{h.serial}</td>
                      <td className="p-3">
                        <Badge status={h.status}>{h.status}</Badge>
                      </td>
                      <td className="p-3">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                          {h.verification_status || 'Verified Asset'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab: Software */}
      {activeTab === 'software' && (
        <div className="card">
          <h2 className="text-base font-bold text-slate-900 mb-4 flex items-center gap-2">
            <KeyRound className="w-4 h-4 text-purple-600" />
            Enterprise Software Subscriptions
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                <tr>
                  <th className="p-3">License ID</th>
                  <th className="p-3">Product Name</th>
                  <th className="p-3">Edition</th>
                  <th className="p-3">Expiry Date</th>
                  <th className="p-3">Status</th>
                  <th className="p-3">Verification</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {verifiedSoftware.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="p-4 text-center text-slate-500">
                      No verified software subscriptions registered.
                    </td>
                  </tr>
                ) : (
                  verifiedSoftware.map((s, i) => (
                    <tr key={i} className="hover:bg-slate-50/60">
                      <td className="p-3 font-mono font-bold text-purple-700">{s.license_id}</td>
                      <td className="p-3 font-semibold text-slate-800">{s.software_name}</td>
                      <td className="p-3 text-slate-600">{s.edition}</td>
                      <td className="p-3 font-mono text-slate-500">{s.expiry_date}</td>
                      <td className="p-3">
                        <Badge status={s.status}>{s.status}</Badge>
                      </td>
                      <td className="p-3">
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                          {s.verification_status || 'Verified License'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Tab: Meeting Rooms */}
      {activeTab === 'rooms' && (
        <div className="card space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Building2 className="w-4 h-4 text-green-600" />
                Physical Meeting Rooms & Facility Suites
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Official verified company meeting rooms registered by Administration.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                {verifiedRooms.length} Verified
              </span>
              {canManageFacilities && (
                <button
                  onClick={handleOpenCreateRoomModal}
                  className="inline-flex items-center gap-1.5 py-1.5 px-3 text-xs font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition"
                >
                  <PlusCircle className="w-3.5 h-3.5" />
                  Add Verified Room
                </button>
              )}
            </div>
          </div>

          {/* Verified Company Meeting Rooms */}
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 mb-3 flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              Verified Company Facilities ({verifiedRooms.length})
            </h3>
            {verifiedRooms.length === 0 ? (
              <div className="p-6 rounded-xl border border-dashed border-slate-300 text-center bg-slate-50/60">
                <Building2 className="w-8 h-8 text-slate-400 mx-auto mb-2 opacity-50" />
                <h4 className="text-sm font-semibold text-slate-700">No Verified Conference Rooms</h4>
                <p className="text-xs text-slate-500 mt-1 max-w-lg mx-auto">
                  No verified company meeting rooms exist in the database. Verified rooms will appear here once registered with physical inspection details by HR or System Administration.
                </p>
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {verifiedRooms.map((r) => (
                  <div key={r.room_id} className="p-4 rounded-xl border border-emerald-200 bg-emerald-50/30 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-mono font-bold text-emerald-800">{r.room_id}</span>
                      <div className="flex items-center gap-1.5">
                        <Badge status="active">Verified Facility</Badge>
                        {canManageFacilities && (
                          <button
                            onClick={() => handleDeleteRoom(r.room_id, r.name)}
                            title="Delete Room"
                            className="p-1 rounded text-slate-400 hover:text-red-600 hover:bg-red-50 transition"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </div>
                    </div>
                    <h4 className="text-sm font-bold text-slate-900">{r.name}</h4>
                    <div className="text-xs text-slate-600 space-y-1">
                      <p><span className="font-semibold text-slate-700">Floor:</span> {r.floor}</p>
                      <p><span className="font-semibold text-slate-700">Capacity:</span> {r.capacity} seats</p>
                      {Array.isArray(r.features) && r.features.length > 0 && (
                        <p><span className="font-semibold text-slate-700">Amenities:</span> {r.features.join(' • ')}</p>
                      )}
                    </div>
                    <div className="pt-2 border-t border-emerald-200/60 text-[11px] text-slate-500">
                      Verified by {r.verified_by_name || 'Admin'} on {r.verified_at ? r.verified_at.split('T')[0] : 'Audit'}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Tab: Seating & Desk Layouts */}
      {activeTab === 'seating' && (
        <div className="card space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <MapPin className="w-4 h-4 text-amber-600" />
                Workstation & Personal Locker Registry
              </h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Official workstation and locker assignments confirmed by Administration.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
                {confirmedSeating.length} Confirmed
              </span>
              {canManageFacilities && (
                <button
                  onClick={handleOpenCreateSeatingModal}
                  className="inline-flex items-center gap-1.5 py-1.5 px-3 text-xs font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition"
                >
                  <PlusCircle className="w-3.5 h-3.5" />
                  Assign Verified Workstation
                </button>
              )}
            </div>
          </div>

          {confirmedSeating.length === 0 ? (
            <div className="p-6 rounded-xl border border-dashed border-slate-300 text-center bg-slate-50/60">
              <MapPin className="w-8 h-8 text-slate-400 mx-auto mb-2 opacity-60" />
              <h4 className="text-sm font-semibold text-slate-700">No Confirmed Workstation Allocations</h4>
              <p className="text-xs text-slate-500 mt-1 max-w-lg mx-auto">
                No verified desk or locker allocations are currently recorded in the system. Workstation assignments appear here only once entered and physically confirmed by Administration.
              </p>
            </div>
          ) : (
            <div>
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                  Workstation & Locker Registry ({confirmedSeating.length} {confirmedSeating.length === 1 ? 'Record' : 'Records'})
                </h3>
                <span className="text-[11px] text-slate-500">
                  Sorted by desk identifier
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-500 font-semibold border-b border-slate-200">
                    <tr>
                      <th className="p-3">Desk Identifier</th>
                      <th className="p-3">Locker No</th>
                      <th className="p-3">Assigned Colleague</th>
                      <th className="p-3">Floor / Zone</th>
                      <th className="p-3">Allocation Status</th>
                      <th className="p-3">Verification State</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {confirmedSeating.map((s, idx) => (
                      <tr key={s.allocation_id || idx} className="hover:bg-slate-50/60">
                        <td className="p-3 font-mono font-bold text-slate-700">
                          {s.desk_number || s.desk || '—'}
                        </td>
                        <td className="p-3 font-mono font-semibold text-slate-600">
                          {s.locker_number || s.locker || '—'}
                        </td>
                        <td className="p-3 font-medium text-slate-800">
                          {s.employee_name || s.name || s.employee_id}
                          {s.employee_id && (
                            <span className="block text-[11px] font-mono text-slate-400">
                              {s.employee_id}
                            </span>
                          )}
                        </td>
                        <td className="p-3 text-slate-600">
                          {[s.floor, s.bay].filter(Boolean).join(' • ') || '—'}
                        </td>
                        <td className="p-3">
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            Allocated
                          </span>
                        </td>
                        <td className="p-3">
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-100 text-emerald-800 border border-emerald-200">
                            Verified ({s.verified_by_name || 'Admin'})
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Modal: Register / Verify Facility Room */}
      {isRoomModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                {selectedRoom ? `Physical Verification: ${selectedRoom.room_id}` : 'Register & Verify Meeting Room'}
              </h3>
              <button
                onClick={() => setIsRoomModalOpen(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-3 rounded-lg bg-blue-50 border border-blue-200 text-xs text-blue-900 flex items-start gap-2.5">
              <ShieldCheck className="w-4 h-4 text-blue-600 shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold">Administrator Physical Audit Requirement</p>
                <p className="text-[11px] text-blue-800 mt-0.5 leading-relaxed">
                  Enter only confirmed, physically inspected room specifications along with mandatory verification audit notes. No default room values are generated automatically.
                </p>
              </div>
            </div>

            <form onSubmit={handleSubmitVerifyRoom} className="space-y-3.5 text-xs">
              <div>
                <label className="font-semibold text-slate-700 block mb-1">Confirmed Room Name *</label>
                <input
                  type="text"
                  required
                  value={verifyRoomName}
                  onChange={(e) => setVerifyRoomName(e.target.value)}
                  placeholder="Enter confirmed meeting room name"
                  className="input-field text-xs w-full"
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Physical Floor *</label>
                  <input
                    type="text"
                    required
                    value={verifyRoomFloor}
                    onChange={(e) => setVerifyRoomFloor(e.target.value)}
                    placeholder="Enter verified physical floor"
                    className="input-field text-xs w-full"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Audited Capacity (Seats) *</label>
                  <input
                    type="number"
                    min="1"
                    required
                    value={verifyRoomCapacity}
                    onChange={(e) => setVerifyRoomCapacity(e.target.value)}
                    placeholder="Enter confirmed seat count"
                    className="input-field text-xs w-full"
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="font-semibold text-slate-700">Verified Equipment & Amenities</label>
                  <span className="text-[10px] text-slate-400">Optional, comma-separated</span>
                </div>
                <input
                  type="text"
                  value={verifyRoomFeatures}
                  onChange={(e) => setVerifyRoomFeatures(e.target.value)}
                  placeholder="Enter verified equipment only if present"
                  className="input-field text-xs w-full"
                />
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="font-semibold text-slate-700">
                    Audit Verification Notes <span className="text-red-500 font-bold">*</span>
                  </label>
                  <span className="text-[10px] text-red-600 font-medium">Mandatory physical evidence</span>
                </div>
                <textarea
                  rows="2"
                  required
                  value={verifyRoomNotes}
                  onChange={(e) => setVerifyRoomNotes(e.target.value)}
                  placeholder="Enter physical inspection details, inspection date, and authorized facility sign-off notes (required)..."
                  className="input-field text-xs w-full"
                />
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsRoomModalOpen(false)}
                  className="btn-secondary py-1.5 px-3 text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary py-1.5 px-4 text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-semibold"
                >
                  Confirm & Mark Verified
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Modal: Assign / Verify Workstation Allocation */}
      {isSeatingModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 backdrop-blur-xs p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-600" />
                {selectedSeating ? `Physical Audit: Workstation ${selectedSeating.allocation_id}` : 'Assign & Verify Workstation'}
              </h3>
              <button
                onClick={() => setIsSeatingModalOpen(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {selectedSeating ? (
              <div className="p-2.5 rounded-lg bg-blue-50 border border-blue-200 text-xs text-blue-900">
                <p className="font-semibold">Colleague:</p>
                <p>{selectedSeating.employee_name} ({selectedSeating.employee_id})</p>
              </div>
            ) : (
              <div>
                <label className="font-semibold text-slate-700 text-xs block mb-1">Colleague (Employee ID) *</label>
                {directoryUsers.length > 0 ? (
                  <select
                    required
                    value={targetEmployeeId}
                    onChange={(e) => setTargetEmployeeId(e.target.value)}
                    className="input-field text-xs w-full"
                  >
                    <option value="">Select verified colleague...</option>
                    {directoryUsers
                      .filter((u) => u.is_active !== false && (u.employee_id || u.emp_id))
                      .map((u) => {
                        const eid = u.employee_id || u.emp_id;
                        return (
                          <option key={eid} value={eid}>
                            {u.full_name || u.name || eid} ({eid})
                          </option>
                        );
                      })}
                  </select>
                ) : (
                  <input
                    type="text"
                    required
                    value={targetEmployeeId}
                    onChange={(e) => setTargetEmployeeId(e.target.value)}
                    placeholder="Enter Employee ID"
                    className="input-field text-xs w-full font-mono"
                  />
                )}
              </div>
            )}

            <form onSubmit={handleSubmitVerifySeating} className="space-y-3.5 text-xs">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Official Desk No *</label>
                  <input
                    type="text"
                    required
                    value={verifyDesk}
                    onChange={(e) => setVerifyDesk(e.target.value)}
                    placeholder="Enter official desk identifier"
                    className="input-field text-xs w-full font-mono"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Official Locker No</label>
                  <input
                    type="text"
                    value={verifyLocker}
                    onChange={(e) => setVerifyLocker(e.target.value)}
                    placeholder="Optional verified locker identifier"
                    className="input-field text-xs w-full font-mono"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Physical Floor *</label>
                  <input
                    type="text"
                    required
                    value={verifyFloor}
                    onChange={(e) => setVerifyFloor(e.target.value)}
                    placeholder="Enter verified floor"
                    className="input-field text-xs w-full"
                  />
                </div>
                <div>
                  <label className="font-semibold text-slate-700 block mb-1">Bay / Zone *</label>
                  <input
                    type="text"
                    required
                    value={verifyBay}
                    onChange={(e) => setVerifyBay(e.target.value)}
                    placeholder="Enter verified zone or bay"
                    className="input-field text-xs w-full"
                  />
                </div>
              </div>

              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="font-semibold text-slate-700">
                    Audit Verification Notes <span className="text-red-500 font-bold">*</span>
                  </label>
                  <span className="text-[10px] text-red-600 font-medium">Mandatory physical evidence</span>
                </div>
                <textarea
                  rows="2"
                  required
                  value={verifySeatingNotes}
                  onChange={(e) => setVerifySeatingNotes(e.target.value)}
                  placeholder="Enter physical workstation verification notes and sign-off details (required)..."
                  className="input-field text-xs w-full"
                />
              </div>

              <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsSeatingModalOpen(false)}
                  className="btn-secondary py-1.5 px-3 text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary py-1.5 px-4 text-xs bg-emerald-600 hover:bg-emerald-700 text-white font-semibold"
                >
                  Confirm & Mark Verified
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};

export default AssetsInventory;
