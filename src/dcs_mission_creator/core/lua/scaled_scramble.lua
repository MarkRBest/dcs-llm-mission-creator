-- Start successive uncontrolled fighter pairs as the live player population grows.
-- A committed pair stays committed if players later disconnect; despawning an
-- airborne threat would be more disruptive than accepting temporary overmatch.
do
  local side = __SIDE__
  local zoneName = __ZONE_NAME__
  local scan = __SCAN_S__
  local flights = {
__FLIGHTS__
  }
  local started = {}

  local function occupiedPlayers()
    local players = coalition.getPlayers(side) or {}
    local live = {}
    for _, unit in ipairs(players) do
      if unit and unit:isExist() and unit:getLife() > 0 then
        live[#live + 1] = unit
      end
    end
    return live
  end

  local function anyInside(players, zone)
    if not zone or not zone.point then return false end
    local radius = zone.radius or 0
    local radiusSq = radius * radius
    for _, unit in ipairs(players) do
      local point = unit:getPoint()
      local dx = point.x - zone.point.x
      local dz = point.z - zone.point.z
      if dx * dx + dz * dz <= radiusSq then return true end
    end
    return false
  end

  local function startFlight(row)
    local group = Group.getByName(row.name)
    if not group or not group:isExist() then return false end
    local controller = group:getController()
    if not controller then return false end
    controller:setCommand({id = "Start", params = {}})
    return true
  end

  local function sweep(_, time)
    local players = occupiedPlayers()
    if anyInside(players, trigger.misc.getZone(zoneName)) then
      for index, row in ipairs(flights) do
        if not started[index] and #players >= row.players and startFlight(row) then
          started[index] = true
        end
      end
    end
    return time + scan
  end

  timer.scheduleFunction(sweep, {}, timer.getTime() + 1)
end
