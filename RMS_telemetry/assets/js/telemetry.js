function updateStatus(response, status, xhr) {
  var sp = document.getElementById('station_id');
  if( sp != null ) {
    sp.innerHTML = response['station_id'];
    sp.classList.remove("loading");
  }
  
  sp = document.getElementById('capture_active');
  if( sp != null ) {
    if( response['capture']['running'] ) {
      sp.innerHTML = 'active'
    } else {
      sp.innerHTML = 'waiting for next start at ' + response['capture']['next_start'];
    }
    sp.classList.remove("loading");
  }
}

function updateLinks(response, status, xhr) {
  sta = response['station_id'];
  cc = sta.slice(0, 2);
  
  var last_week = new Date();
  last_week.setDate(last_week.getDate() - 7);
  var lw_str = last_week.getFullYear() + "-" + (last_week.getMonth() + 1) + "-" + last_week.getDay();
  
  var ln = document.getElementById('weblog');
  if( ln != null ) {
    ln.innerHTML = 'Weblog Entry <i class="fa fa-external-link" aria-hidden="true"></i>';
    ln.href = "https://globalmeteornetwork.org/weblog/" + cc + "/" + sta + "/latest/";
    ln.classList.remove("loading");
  }
  
  ln = document.getElementById('recent_contrib');
  if( ln != null ) {
    ln.innerHTML = 'Recent Contributions <i class="fa fa-external-link" aria-hidden="true"></i>';
    ln.href = "https://explore.globalmeteornetwork.org/gmn_data_store/participating_station?created_at__gte=" + lw_str + "&station_code__exact=" + sta + "&_sort_desc=created_at";
    ln.classList.remove("loading");
  }
  
  ln = document.getElementById('recent_enable');
  if( ln != null ) {
    ln.innerHTML = "Recently Enabled (" + response['station_id'] + " + One Other Station) <i class=\"fa fa-external-link\" aria-hidden=\"true\"></i>";
    ln.href = "https://explore.globalmeteornetwork.org/gmn_data_store/-/query?sql=SELECT+ps_summary.meteor_unique_trajectory_identifier%2C%0D%0A+++++++REPLACE%28REPLACE%28ps_summary.stations%2C+%3Ap0%2C+%27%27%29%2C+%27%2C%27%2C+%27%27%29+as+other_station%2C%0D%0A+++++++m.beginning_utc_time%2C%0D%0A+++++++m.elev_deg%2C%0D%0A+++++++m.latbeg_n_deg%2C%0D%0A+++++++m.lonbeg_e_deg%2C%0D%0A+++++++m.latend_n_deg%2C%0D%0A+++++++m.lonend_e_deg%2C%0D%0A+++++++m.htbeg_km%2C%0D%0A+++++++m.htend_km%2C%0D%0A+++++++m.duration_sec%2C%0D%0A+++++++m.peak_absmag%2C%0D%0A+++++++m.vgeo_km_s%2C%0D%0A+++++++m.created_at+as+meteor_created_at%2C%0D%0A+++++++m.updated_at+as+meteor_updated_at%0D%0AFROM+%28%0D%0A++++SELECT+meteor_unique_trajectory_identifier%2C+%0D%0A+++++++++++GROUP_CONCAT%28station_code%29+as+stations%2C%0D%0A+++++++++++COUNT%28*%29+as+station_count%2C%0D%0A+++++++++++MAX%28created_at%29+as+latest_created_at%0D%0A++++FROM+participating_station+%0D%0A++++WHERE+meteor_unique_trajectory_identifier+IN+%28%0D%0A++++++++SELECT+meteor_unique_trajectory_identifier+%0D%0A++++++++FROM+participating_station+%0D%0A++++++++WHERE+station_code+%3D+%3Ap0%0D%0A++++%29%0D%0A++++GROUP+BY+meteor_unique_trajectory_identifier%0D%0A++++HAVING+COUNT%28DISTINCT+station_code%29+%3D+2%0D%0A%29+ps_summary%0D%0AJOIN+meteor+m+ON+ps_summary.meteor_unique_trajectory_identifier+%3D+m.unique_trajectory_identifier%0D%0AORDER+BY+ps_summary.latest_created_at+DESC%0D%0ALIMIT+101%3B&p0=" + sta + "&p1=" + lw_str;
    ln.classList.remove("loading");
  }
}

function fetchLatest() {
  $.ajax({'url': '/latest',
          'success': function(response, status, xhr) {
            updateStatus(response, status, xhr);
            updateLinks(response, status, xhr);
            setTimeout(fetchLatest, 30000);
          },
          'error': function() {
            setTimeout(fetchLatest, 30000);
          }
         });
}

function updatePrevious(response, status, xhr) {
  var sp = document.getElementById('last_capture');
  if( sp != null ) {
    sp.innerHTML = response['capture']['started'];
    sp.classList.remove("loading");
  }
  
  var astr_ok = response['camera']['astrometry_good'];
  var phot_ok = response['camera']['photometry_good'];
  var msg = '';
  if( astr_ok && phot_ok ) {
    msg = 'OK';
  } else if( astr_ok && !phot_ok ) {
    msg = 'photometry failed';
  } else if( !astr_ok && phot_ok ) {
    msg = 'astrometry failed';
  } else {
    msg = "astrometry and photometry failed";
  }
  sp = document.getElementById('last_overall');
  if( sp != null ) {
    sp.innerHTML = msg;
    if( msg === 'OK' ) {
      sp.classList.remove('error');
    } else {
      sp.classList.add('error');
    }
    sp.classList.remove('loading');
  }
}

function fetchPrevious() {
  $.ajax({'url': '/previous',
          'success': function(response, status, xhr) {
            updatePrevious(response, status, xhr);
            setTimeout(fetchPrevious, 900000);
          },
          'error': function() {
            setTimeout(fetchPrevious, 900000);
          }
         });
}

function updateHistory(response, status, xhr) {
  var contents = '';
  for (let idx = response.length - 1; idx >= 0; idx--) {
    var date = response[idx];
    var date_str = date.slice(0,4) + "-" + date.slice(4,6) + "-" + date.slice(6,8);
    var entry = date_str;
    entry += ' - <a href="/latest?date=' + date + '">Detailed Status</a>';
    entry += ' - <a href="/latest/image?date=' + date + '">Stacked Meteors Image</a><br />';
    contents += entry;
  }
  
  var dv = document.getElementById('history_listing');
  if( dv != null ) {
    dv.innerHTML = contents;
    dv.classList.remove('loading');
  }
}

function fetchHistory() {
  $.ajax({'url': '/previous/dates',
          'success': function(response, status, xhr) {
            updateHistory(response, status, xhr);
            setTimeout(fetchHistory, 900000);
          },
          'error': function() {
            setTimeout(fetchHistory, 900000);
          }
         });
}

function initializePage() {
  fetchLatest();
  fetchPrevious();
  fetchHistory();
}
