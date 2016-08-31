import logging
import numpy as np
import analysis
import creation
import plots
import randomwalk
import run
import time
from mpi4py import MPI


def serial_method(grid_size, tube_length, tube_radius, num_tubes, orientation, tot_time, quiet, plot_save_dir,
                  gen_plots, kapitza, prob_m_cn, tot_walkers, printout_inc, k_conv_error_buffer):
    def histogram_walker_list(hot_walker_master, cold_walker_master):
        H = np.zeros((grid.size + 1, grid.size + 1, grid.size + 1))  # resets H every time function is called, IMPORTANT
        for i in range(len(hot_walker_master)):
            hot_temp = hot_walker_master[i]
            H[hot_temp.pos[-1][0], hot_temp.pos[-1][1], hot_temp.pos[-1][2]] += 1

            cold_temp = cold_walker_master[i]
            H[cold_temp.pos[-1][0], cold_temp.pos[-1][1], cold_temp.pos[-1][2]] -= 1
        # DEBUG, sum should be 0
        # print np.sum(H), np.max(H), np.min(H)
        return H

    grid = creation.Grid3D_onlat(grid_size, tube_length, num_tubes, orientation, tube_radius)
    if gen_plots:
        plots.plot_three_d_random_walk_setup(grid, quiet, plot_save_dir)

    grid_range = [[0, grid.size + 1], [0, grid.size + 1], [0, grid.size + 1]]
    bins = grid.size + 1

    start = time.clock()

    # these will hold the walker objects, need to access walker.pos for the positions
    hot_walker_master = []
    cold_walker_master = []
    k_list = []
    k_err_list = []
    dt_dx_list = []
    heat_flux_list = []
    timestep_list = []  # x axis for plots
    xedges = range(0, bins)
    yedges = range(0, bins)
    zedges = range(0, bins)
    start_k_err_check = tot_time / 2

    # d_add - how often to add a hot/cold walker pair
    d_add = tot_time / (tot_walkers / 2.0)  # as a float
    if d_add.is_integer() and d_add >= 1:
        d_add = int(tot_time / (tot_walkers / 2.0))
        walker_frac_trigger = 0  # add a pair every d_add timesteps
    elif d_add < 1:  # this is a fractional number < 1, implies more than 1 walker pair should be added every timestep
        d_add = int(1.0 / d_add)
        walker_frac_trigger = 1
    else:  # change num_walkers or timesteps
        logging.error('Choose tot_time / (tot_walkers / 2.0) so that it is integer or less than 1')
        raise SystemExit
    if walker_frac_trigger == 1:
        logging.info('Adding %d hot/cold walker pair(s) every timestep, this might not converge' % d_add)
    elif walker_frac_trigger == 0:
        logging.info('Adding 1 hot/cold walker pair(s) every %d timesteps' % d_add)

    for i in range(tot_time):
        if (i % printout_inc) == 0 and (i >= (2 * printout_inc)):
            cur_num_walkers = len(hot_walker_master) * 2
            Htemp = histogram_walker_list(hot_walker_master, cold_walker_master)
            dt_dx, heat_flux, dt_dx_err, k, k_err, r2, temp_profile_sum = analysis.check_convergence_3d_onlat(Htemp,
                                                                                                              cur_num_walkers,
                                                                                                              grid.size,
                                                                                                              i)
            k_list.append(k)
            dt_dx_list.append(dt_dx)
            heat_flux_list.append(heat_flux)
            timestep_list.append(i)
            if i >= start_k_err_check:
                k_err = np.std(k_list[-k_conv_error_buffer:], ddof=1)
                k_err_list.append(k_err)
                logging.info("Timestep: %d, %d walkers, R2: %.4f, k: %.4E, k err: %.4E, heat flux: %.4E, dT(x)/dx: %.4E"
                             % (i, cur_num_walkers, r2, k, k_err, heat_flux, dt_dx))
            else:
                logging.info("Timestep: %d, %d walkers, R2: %.4f, k: %.4E, heat flux: %.4E, dT(x)/dx: %.4E"
                             % (i, cur_num_walkers, r2, k, heat_flux, dt_dx))
        if walker_frac_trigger == 0:
            if (i % d_add) == 0:
                trigger = 1
                # let's add the 2 new walkers
                hot_walker_temp = creation.Walker3D_onlat(grid.size, 'hot')
                cold_walker_temp = creation.Walker3D_onlat(grid.size, 'cold')
                hot_walker_master.append(hot_walker_temp)
                cold_walker_master.append(cold_walker_temp)
            else:
                trigger = 0
        elif walker_frac_trigger == 1:
            trigger = d_add  # trigger never 0 in this case
            # let's add the 2 new walkers, several times
            for k in range(d_add):
                hot_walker_temp = creation.Walker3D_onlat(grid.size, 'hot')
                cold_walker_temp = creation.Walker3D_onlat(grid.size, 'cold')
                hot_walker_master.append(hot_walker_temp)
                cold_walker_master.append(cold_walker_temp)
        # let's update all the positions of the activated walkers
        for j in range(len(hot_walker_master) - trigger):  # except the new ones
            hot_temp = hot_walker_master[j]
            current_hot_updated = randomwalk.apply_moves_3d(hot_temp, kapitza, grid, prob_m_cn)
            current_hot_updated.erase_prev_pos()
            hot_walker_master[j] = current_hot_updated

            cold_temp = cold_walker_master[j]
            current_cold_updated = randomwalk.apply_moves_3d(cold_temp, kapitza, grid, prob_m_cn)
            current_cold_updated.erase_prev_pos()
            cold_walker_master[j] = current_cold_updated

    # let's histogram everything
    logging.info('Finished random walks, histogramming...')

    H = histogram_walker_list(hot_walker_master, cold_walker_master)

    dt_dx, heat_flux, dt_dx_err, k, k_err, r2, temp_profile_sum = analysis.check_convergence_3d_onlat(H, tot_walkers,
                                                                                                      grid.size,
                                                                                                      tot_time)
    logging.info("%d walkers: R squared: %.4f, k: %.4E, heat flux: %.4E, dT(x)/dx: %.4E" % (tot_walkers, r2, k,
                                                                                            heat_flux, dt_dx))

    end = time.clock()
    logging.info("Constant flux simulation has completed")
    logging.info("Serial simulation time was %.4f s" % (end - start))

    temp_profile = plots.plot_histogram_walkers_onlat(grid, tot_time, temp_profile_sum, xedges, yedges, quiet,
                                                      plot_save_dir,
                                                      gen_plots)
    if gen_plots:
        plots.plot_k_convergence(k_list, quiet, plot_save_dir, timestep_list)
        plots.plot_k_convergence_err(k_list, quiet, plot_save_dir, start_k_err_check, timestep_list)
        plots.plot_dt_dx(dt_dx_list, quiet, plot_save_dir, timestep_list)
        plots.plot_heat_flux(heat_flux_list, quiet, plot_save_dir, timestep_list)
        temp_gradient_x = plots.plot_temp_gradient_2d_onlat(grid, temp_profile, xedges, yedges, quiet,
                                                            plot_save_dir, gradient_cutoff=0)
        gradient_avg, gradient_std = plots.plot_linear_temp(temp_profile, grid_size, quiet, plot_save_dir,
                                                            gen_plots)
    logging.info("Complete")







def sim_3d_onlat(grid_size, tube_length, tube_radius, num_tubes, orientation, timesteps, save_loc_data,
                 quiet, save_loc_plots, save_dir, k_convergence_tolerance, begin_cov_check,
                 k_conv_error_buffer, plot_save_dir, gen_plots, kapitza, prob_m_cn, run_to_convergence, num_walkers):
    walker_data_save_dir = plot_save_dir + "/walker_locations"
    walker_plot_save_dir = plot_save_dir + "/walker_plots"

    grid = creation.Grid3D_onlat(grid_size, tube_length, num_tubes, orientation, tube_radius)
    if gen_plots:
        plots.plot_three_d_random_walk_setup(grid, quiet, plot_save_dir)

    grid_range = [[0, grid.size + 1], [0, grid.size + 1], [0, grid.size + 1]]
    bins = grid.size + 1
    H = np.zeros((grid.size + 1, grid.size + 1, grid.size + 1), dtype=int)

    i = 0
    k_list = []
    dt_dx_list = []
    heat_flux_list = []
    k_convergence_err_list = []
    k_convergence_err = 1.0
    x_edges = range(0, bins)
    y_edges = range(0, bins)

    if run_to_convergence:
        while k_convergence_err > k_convergence_tolerance:
            walker, H, x_edges, y_edges, z_edges = randomwalk_routine_3d_serial(grid, grid_range, timesteps,
                                                                                save_loc_data, quiet, save_loc_plots,
                                                                                bins, plot_save_dir,
                                                                                walker_plot_save_dir,
                                                                                walker_data_save_dir, gen_plots,
                                                                                kapitza, prob_m_cn, i, H)

            i += 1

            dt_dx, heat_flux, dt_dx_err, k, k_err, r2, temp_profile_sum = analysis.check_convergence_3d_onlat(H, i * 2,
                                                                                                              grid.size,
                                                                                                              timesteps)
            k_list.append(k)
            heat_flux_list.append(heat_flux)
            dt_dx_list.append(dt_dx)
            logging.info("%d: R squared: %.4f, k: %.4E" % (i, r2, k))
            if i > begin_cov_check:
                k_convergence_err = np.std(np.array(k_list[-k_conv_error_buffer:]), ddof=1)
                k_convergence_val = np.mean(np.array(k_list[-k_conv_error_buffer:]))
                k_convergence_err_list.append(k_convergence_err)
                logging.info("k: %.4E" % k_convergence_val)
                logging.info("k error: %.4E" % k_convergence_err)
    else:
        for i in range(num_walkers / 2):
            walker, H, x_edges, y_edges, z_edges = randomwalk_routine_3d_serial(grid, grid_range, timesteps,
                                                                                save_loc_data, quiet, save_loc_plots,
                                                                                bins, plot_save_dir,
                                                                                walker_plot_save_dir,
                                                                                walker_data_save_dir, gen_plots,
                                                                                kapitza, prob_m_cn, i, H)

            dt_dx, heat_flux, dt_dx_err, k, k_err, r2, temp_profile_sum = analysis.check_convergence_3d_onlat(H, i * 2,
                                                                                                              grid.size,
                                                                                                              timesteps)
            k_list.append(k)
            dt_dx_list.append(dt_dx)
            heat_flux_list.append(heat_flux)
            logging.info("%d: R squared: %.4f, k: %.4E" % (i, r2, k))
            if i > begin_cov_check:
                k_convergence_err = np.std(np.array(k_list[-k_conv_error_buffer:]), ddof=1)
                k_convergence_val = np.mean(np.array(k_list[-k_conv_error_buffer:]))
                k_convergence_err_list.append(k_convergence_err)
                logging.info("k: %.4E" % k_convergence_val)
                logging.info("k error: %.4E" % k_convergence_err)

    logging.info("Simulation has converged with %d total walkers" % (i * 2))
    logging.info("Finished random walks")
    if gen_plots:
        temp_profile = plots.plot_histogram_walkers_onlat(grid, timesteps, temp_profile_sum, x_edges, y_edges,
                                                             quiet, plot_save_dir, gen_plots)
        plots.plot_k_convergence(k_list, quiet, plot_save_dir)
        plots.plot_k_convergence_err(k_convergence_err_list, quiet, plot_save_dir, begin_cov_check)
        plots.plot_dt_dx(dt_dx_list, quiet, plot_save_dir)
        plots.plot_heat_flux(heat_flux_list, quiet, plot_save_dir)
        gradient_avg, gradient_std = plots.plot_linear_temp(temp_profile_sum, grid_size, quiet, plot_save_dir,
                                                            gen_plots)
        temp_gradient_x = plots.plot_temp_gradient_2d_onlat(grid, temp_profile_sum, x_edges, y_edges, quiet,
                                                            plot_save_dir, gradient_cutoff=0)
    analysis.final_conductivity_3d_onlat(i * 2, grid.size, timesteps, gradient_avg,
                                         gradient_std, k_convergence_err, num_tubes, save_dir,
                                         k_convergence_val, prob_m_cn, gradient_cutoff=0)
    max_temp = np.max(temp_profile_sum)
    min_temp = np.min(temp_profile_sum)
    diff_temp = np.abs(max_temp) - np.abs(min_temp)
    logging.info("Max temp is %d, min temp is %d, with difference %d" % (max_temp, min_temp, diff_temp))
    logging.info("Complete")


def sim_3d_onlat_MPI(grid_size, tube_length, tube_radius, num_tubes, orientation, timesteps, save_loc_data,
                     quiet, save_loc_plots, save_dir, k_convergence_tolerance, begin_cov_check,
                     k_conv_error_buffer, plot_save_dir, gen_plots, kapitza, prob_m_cn, rank, size, run_to_convergence,
                     num_walkers):
    comm = MPI.COMM_WORLD
    walker_data_save_dir = plot_save_dir + "/walker_locations"
    walker_plot_save_dir = plot_save_dir + "/walker_plots"

    if rank == 0:
        grid = creation.Grid3D_onlat(grid_size, tube_length, num_tubes, orientation, tube_radius)
        if gen_plots:
            plots.plot_three_d_random_walk_setup(grid, quiet, plot_save_dir)
    else:
        grid = None

    grid = comm.bcast(grid, root=0)

    grid_range = [[0, grid.size + 1], [0, grid.size + 1], [0, grid.size + 1]]
    bins = grid.size + 1
    H = np.zeros((grid.size + 1, grid.size + 1, grid.size + 1), dtype=int)
    tot_H = np.zeros((grid.size + 1, grid.size + 1, grid.size + 1), dtype=int)

    i = 0

    k_list = []
    dt_dx_list = []
    heat_flux_list = []
    k_convergence_err_list = []
    k_convergence_err = 1.0
    x_edges = range(0, bins)
    y_edges = range(0, bins)

    start = MPI.Wtime()
    if run_to_convergence:
        while k_convergence_err > k_convergence_tolerance:
            walker, H, x_edges, y_edges, z_edges, tot_H = randomwalk_routine_3d_MPI(grid, grid_range, timesteps,
                                                                                    save_loc_data, quiet,
                                                                                    save_loc_plots, bins,
                                                                                    plot_save_dir,
                                                                                    walker_plot_save_dir,
                                                                                    walker_data_save_dir, gen_plots,
                                                                                    kapitza, prob_m_cn, i, H, rank,
                                                                                    comm, tot_H)

            i += 1

            if rank == 0:
                dt_dx, heat_flux, dt_dx_err, k, k_err, r2, temp_profile_sum = analysis.check_convergence_3d_onlat(tot_H,
                                                                                                                  i * 2 * size,
                                                                                                                  grid.size,
                                                                                                                  timesteps)
                k_list.append(k)
                heat_flux_list.append(heat_flux)
                dt_dx_list.append(dt_dx)
                logging.info("%d: R squared: %.4f, k: %.4E" % (i * size, r2, k))

            comm.Barrier()

            if (i * size) > begin_cov_check:
                if rank == 0:
                    k_convergence_err = np.std(np.array(k_list[-k_conv_error_buffer:]), ddof=1)
                    k_convergence_val = np.mean(np.array(k_list[-k_conv_error_buffer:]))
                    k_convergence_err_list.append(k_convergence_err)
                    logging.info("k: %.4E" % k_convergence_val)
                    logging.info("k error: %.4E" % k_convergence_err)
                else:
                    k_convergence_err = None
                    k_convergence_val = None

                k_convergence_err = comm.bcast(k_convergence_err, root=0)
                k_convergence_val = comm.bcast(k_convergence_val, root=0)

            comm.Barrier()
    else:
        for i in range(num_walkers / (2 * size)):  # rounds down total walkers slightly
            walker, H, x_edges, y_edges, z_edges, tot_H = randomwalk_routine_3d_MPI(grid, grid_range, timesteps,
                                                                                    save_loc_data, quiet,
                                                                                    save_loc_plots, bins,
                                                                                    plot_save_dir,
                                                                                    walker_plot_save_dir,
                                                                                    walker_data_save_dir, gen_plots,
                                                                                    kapitza, prob_m_cn, i, H, rank,
                                                                                    comm, tot_H)
            if rank == 0:
                dt_dx, heat_flux, dt_dx_err, k, k_err, r2, temp_profile_sum = \
                    analysis.check_convergence_3d_onlat(tot_H, i * 2 * size, grid.size, timesteps)
                k_list.append(k)
                dt_dx_list.append(dt_dx)
                heat_flux_list.append(heat_flux)
                logging.info("%d: R squared: %.4f, k: %.4E" % (i * size, r2, k))

            comm.Barrier()

            if (i * size) > begin_cov_check:
                if rank == 0:
                    k_convergence_err = np.std(np.array(k_list[-k_conv_error_buffer:]), ddof=1)
                    k_convergence_val = np.mean(np.array(k_list[-k_conv_error_buffer:]))
                    k_convergence_err_list.append(k_convergence_err)
                    logging.info("k: %.4E" % k_convergence_val)
                    logging.info("k error: %.4E" % k_convergence_err)
                else:
                    k_convergence_err = None
                    k_convergence_val = None

                k_convergence_err = comm.bcast(k_convergence_err, root=0)
                k_convergence_val = comm.bcast(k_convergence_val, root=0)

            comm.Barrier()

    if rank == 0:
        end = MPI.Wtime()
        logging.info("Simulation has converged with %d total walkers" % (i * 2 * size))
        logging.info("Finished random walks")
        logging.info("Using %d cores, parallel simulation time was %.4f s" % (size, end - start))
        walk_sec = (i * 2 * size) / (end - start)
        logging.info("Crunched %.4f walkers/second" % walk_sec)
        if gen_plots:
            temp_profile = plots.plot_histogram_walkers_onlat(grid, timesteps, temp_profile_sum, x_edges, y_edges,
                                                                 quiet, plot_save_dir, gen_plots)
            plots.plot_k_convergence(k_list, quiet, plot_save_dir)
            plots.plot_k_convergence_err(k_convergence_err_list, quiet, plot_save_dir, begin_cov_check)
            plots.plot_dt_dx(dt_dx_list, quiet, plot_save_dir)
            plots.plot_heat_flux(heat_flux_list, quiet, plot_save_dir)
            gradient_avg, gradient_std = plots.plot_linear_temp(temp_profile_sum, grid_size, quiet,
                                                                plot_save_dir, gen_plots)
            temp_gradient_x = plots.plot_temp_gradient_2d_onlat(grid, temp_profile_sum, x_edges, y_edges, quiet,
                                                                plot_save_dir, gradient_cutoff=0)
        analysis.final_conductivity_3d_onlat(i * 2 * size, grid.size, timesteps, gradient_avg, gradient_std,
                                             k_convergence_err, num_tubes, plot_save_dir, k_convergence_val,
                                             prob_m_cn, gradient_cutoff=0)
        max_temp = np.max(temp_profile_sum)
        min_temp = np.min(temp_profile_sum)
        diff_temp = np.abs(max_temp) - np.abs(min_temp)
        logging.info("Max temp is %d, min temp is %d, with difference %d" % (max_temp, min_temp, diff_temp))
        logging.info("Complete")


def randomwalk_routine_3d_serial(grid, grid_range, timesteps, save_loc_data, quiet, save_loc_plots, bins, plot_save_dir,
                                 walker_plot_save_dir, walker_data_save_dir, gen_plots, kapitza, prob_m_cn,
                                 i, H):
    # run hot walker
    # logging.info("Start hot walker %d" % (i+1))
    walker = randomwalk.runrandomwalk_3d_onlat(grid, timesteps, 'hot', kapitza, prob_m_cn)
    if save_loc_data:
        run.save_walker_loc(walker, walker_data_save_dir, i, 'hot')
    if i == 0 & save_loc_plots == False & gen_plots == True:  # always save one example trajectory plot
        plots.plot_walker_path_3d_onlat(walker, grid.size, 'hot', quiet, i + 1, plot_save_dir)
    elif save_loc_plots & gen_plots == True:
        plots.plot_walker_path_3d_onlat(walker, grid.size, 'hot', quiet, i + 1, walker_plot_save_dir)
    H_temp, x_edges, y_edges, z_edges = plots.histogram_walker_3d_onlat(walker, grid_range, bins)
    H += H_temp

    # run cold walker
    # logging.info("Start cold walker %d" % (i+1))
    walker = randomwalk.runrandomwalk_3d_onlat(grid, timesteps, 'cold', kapitza, prob_m_cn)
    if save_loc_data:
        run.save_walker_loc(walker, walker_data_save_dir, i, 'cold')
    if i == 0 & save_loc_plots == False & gen_plots == True:
        plots.plot_walker_path_3d_onlat(walker, grid.size, 'cold', quiet, i + 1, plot_save_dir)
    elif save_loc_plots & gen_plots == True:
        plots.plot_walker_path_3d_onlat(walker, grid.size, 'cold', quiet, i + 1, walker_plot_save_dir)
    H_temp, x_edges, y_edges, z_edges = plots.histogram_walker_3d_onlat(walker, grid_range, bins)
    H -= H_temp

    return walker, H, x_edges, y_edges, z_edges


def randomwalk_routine_3d_MPI(grid, grid_range, timesteps, save_loc_data, quiet, save_loc_plots, bins, plot_save_dir,
                              walker_plot_save_dir, walker_data_save_dir, gen_plots, kapitza, prob_m_cn,
                              i, H, rank, comm, tot_H):
    # run hot walker
    # logging.info("Start hot walker %d" % (i+1))
    walker = randomwalk.runrandomwalk_3d_onlat(grid, timesteps, 'hot', kapitza, prob_m_cn)

    if rank == 0:
        if save_loc_data:
            run.save_walker_loc(walker, walker_data_save_dir, i, 'hot')
        if i == 0 & save_loc_plots == False & gen_plots == True:  # always save one example trajectory plot
            plots.plot_walker_path_3d_onlat(walker, grid.size, 'hot', quiet, i + 1, plot_save_dir)
        elif save_loc_plots & gen_plots == True:
            plots.plot_walker_path_3d_onlat(walker, grid.size, 'hot', quiet, i + 1, walker_plot_save_dir)

    H_temp, x_edges, y_edges, z_edges = plots.histogram_walker_3d_onlat(walker, grid_range, bins)
    H += H_temp

    # run cold walker
    # logging.info("Start cold walker %d" % (i+1))
    walker = randomwalk.runrandomwalk_3d_onlat(grid, timesteps, 'cold', kapitza, prob_m_cn)

    if rank == 0:
        if save_loc_data:
            run.save_walker_loc(walker, walker_data_save_dir, i, 'cold')
        if i == 0 & save_loc_plots == False & gen_plots == True:
            plots.plot_walker_path_3d_onlat(walker, grid.size, 'cold', quiet, i + 1, plot_save_dir)
        elif save_loc_plots & gen_plots == True:
            plots.plot_walker_path_3d_onlat(walker, grid.size, 'cold', quiet, i + 1, walker_plot_save_dir)

    H_temp, x_edges, y_edges, z_edges = plots.histogram_walker_3d_onlat(walker, grid_range, bins)
    H -= H_temp

    comm.Reduce(H, tot_H, op=MPI.SUM, root=0)
    # H is updated on every core for every i independently
    # tot_H is the total across all cores

    comm.Barrier()

    return walker, H, x_edges, y_edges, z_edges, tot_H
